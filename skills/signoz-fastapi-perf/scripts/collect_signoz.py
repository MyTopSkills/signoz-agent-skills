#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SigNoz v5 HTTP slow-request + trace-span analyzer (read-only).

Python >= 3.9; dependency: requests

Example:
  export SIGNOZ_API_KEY='...'
  python3 scripts/collect_signoz.py --url https://signoz.example.com \
      --service my-fastapi-service --hours 24 --threshold-ms 5000 --limit 100

Notes:
- No writes to SigNoz, MongoDB, S3 or application services.
- All timings are observational. Overlapping spans are NOT added to wall-clock.
- Uncovered time != CPU time; it may contain uninstrumented I/O or work.
- The shape of query-range responses and field keys may vary by SigNoz version.
"""

import argparse
import collections
import csv
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    sys.exit("缺少依赖 requests；请运行 python3 -m pip install requests")

BASE_FIELDS = [
    ("timestamp", "span"), ("trace_id", "span"), ("span_id", "span"),
    ("parent_span_id", "span"), ("name", "span"),
    ("service.name", "resource"), ("kind_string", "span"),
    ("duration_nano", "span"), ("http_method", "span"),
    ("response_status_code", "span"),
]
EXTRA_FIELDS = [
    ("db.system", "attribute"), ("db.operation", "attribute"),
    ("db.mongodb.collection", "attribute"), ("db.name", "attribute"),
    ("http.route", "attribute"), ("http.url", "attribute"),
    ("net.peer.name", "attribute"),
]
HTTP_METHOD = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE)\s+[/\w]", re.I)


def val(row: Dict[str, Any], *names, default=None):
    for key in names:
        if key in row and row[key] is not None:
            return row[key]
    attrs = row.get("attributes") or row.get("tags") or {}
    if isinstance(attrs, dict):
        for key in names:
            if key in attrs and attrs[key] is not None:
                return attrs[key]
    return default


def as_num(v, default=0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


def ns_of_timestamp(v) -> int:
    if v is None or v == "":
        return 0
    if isinstance(v, str) and not re.fullmatch(r"\d+(?:\.\d+)?", v):
        try:
            parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1e9)
        except ValueError:
            return 0
    x = as_num(v)
    if x > 1e17:  # nanoseconds
        return int(x)
    if x > 1e14:  # microseconds
        return int(x * 1e3)
    if x > 1e11:  # milliseconds
        return int(x * 1e6)
    if x > 1e8:   # seconds
        return int(x * 1e9)
    return 0


def ns_of_duration(v) -> int:
    if isinstance(v, str) and v.endswith("ms"):
        return int(as_num(v[:-2]) * 1e6)
    if isinstance(v, str) and v.endswith("s"):
        return int(as_num(v[:-1]) * 1e9)
    return int(as_num(v))


def timestamp_text(v) -> str:
    ns = ns_of_timestamp(v)
    if not ns:
        return str(v or "")
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def unpack_rows(document: Any) -> List[Dict[str, Any]]:
    """Parse documented v5 data.data.results[].rows[].data envelope."""
    body = document
    for _ in range(4):
        if isinstance(body, dict) and isinstance(body.get("data"), dict):
            body = body["data"]
        else:
            break
    results = body.get("results") if isinstance(body, dict) else None
    if results is None and isinstance(body, dict) and isinstance(body.get("rows"), list):
        results = [body]
    if not isinstance(results, list):
        raise ValueError("无法识别 v5 查询响应：缺少 data.data.results，请使用 --debug-response 保存响应排查")
    output = []
    for result in results:
        if not isinstance(result, dict):
            continue
        for row in result.get("rows") or []:
            if not isinstance(row, dict):
                continue
            item = row.get("data") if isinstance(row.get("data"), dict) else row
            output.append(item)
    return output


def intervals_union_ms(intervals: List[tuple], *, within=None) -> float:
    intervals = [(max(a, within[0]), min(b, within[1])) for a, b in intervals] if within else intervals
    intervals = sorted((a, b) for a, b in intervals if b > a)
    if not intervals:
        return 0.0
    total = 0
    lo, hi = intervals[0]
    for a, b in intervals[1:]:
        if a > hi:
            total += hi - lo
            lo, hi = a, b
        else:
            hi = max(hi, b)
    total += hi - lo
    return total / 1e6


def uncovered_intervals(root, spans, minimum_ms=0):
    start = root["start_ns"]
    end = start + root["duration_ns"]
    clips = sorted((max(start, s["start_ns"]), min(end, s["start_ns"] + s["duration_ns"]))
                   for s in spans if s["span_id"] != root["span_id"] and s["duration_ns"] > 0)
    gaps = []
    cursor = start
    for a, b in clips:
        if a > cursor and a - cursor >= minimum_ms * 1e6:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < end and end - cursor >= minimum_ms * 1e6:
        gaps.append((cursor, end))
    return gaps


def classify(s) -> str:
    name = s["name"].lower()
    db = str(s.get("db_system", "")).lower()
    if "mongo" in db or ".find" in name or ".aggregate" in name or ".update" in name or ".insert" in name or "findandmodify" in name:
        return "MongoDB"
    if "opensearch" in name or "elasticsearch" in name:
        return "OpenSearch"
    if "s3." in name or "s3/" in name or any(k in name for k in ("putobject", "getobject", "headobject")):
        return "S3"
    if "redis" in name or "cache" in name:
        return "Redis/Cache"
    if s["kind"].lower() == "client" or name.startswith(("http ", "https://")):
        return "External HTTP/Client"
    if s["kind"].lower() == "server":
        return "HTTP Server"
    return "Business/Other"


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "trace_id": str(val(raw, "trace_id", "traceId", default="")),
        "span_id": str(val(raw, "span_id", "spanId", default="")),
        "parent_span_id": str(val(raw, "parent_span_id", "parentSpanID", "parentSpanId", default="")),
        "name": str(val(raw, "name", default="")),
        "service": str(val(raw, "service.name", "service_name", "serviceName", default="")),
        "kind": str(val(raw, "kind_string", "span_kind", "kind", default="")),
        "start_ns": ns_of_timestamp(val(raw, "timestamp", "start_time", "startTime", default=0)),
        "duration_ns": ns_of_duration(val(raw, "duration_nano", "durationNano", default=0)),
        "method": str(val(raw, "http_method", "http.request.method", default="")),
        "status": str(val(raw, "response_status_code", "http.status_code", "http.response.status_code", default="")),
        "db_system": str(val(raw, "db.system", default="")),
        "collection": str(val(raw, "db.mongodb.collection", "db.collection.name", default="")),
        "db_operation": str(val(raw, "db.operation", "db.operation.name", default="")),
    }
    row["category"] = classify(row)
    return row


def is_http_server(span: Dict[str, Any]) -> bool:
    return span["kind"].lower() == "server" and bool(span["method"] or HTTP_METHOD.match(span["name"]))


def api_payload(start_ms: int, end_ms: int, filter_expression: str,
                offset: int, limit: int, include_extra: bool,
                sort_field: str = "duration_nano"):
    fields = BASE_FIELDS + (EXTRA_FIELDS if include_extra else [])
    return {
        "schemaVersion": "v1",
        "start": start_ms,
        "end": end_ms,
        "requestType": "raw",
        "compositeQuery": {"queries": [{
            "type": "builder_query",
            "spec": {
                "name": "A", "signal": "traces",
                "filter": {"expression": filter_expression},
                "selectFields": [{"name": k, "fieldContext": context} for k, context in fields],
                "order": [{"key": {"name": sort_field, "fieldContext": "span"}, "direction": "desc"}],
                "limit": limit, "offset": offset, "disabled": False,
            },
        }]},
    }


class Client:
    def __init__(self, url: str, api_key: str, debug_response: str = ""):
        self.url = url.rstrip("/")
        self.debug_response = debug_response
        self.session = requests.Session()
        self.session.headers.update({
            "SIGNOZ-API-KEY": api_key, "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "signoz-slow-trace-analyzer/1.0",
        })
        retry = Retry(total=3, status_forcelist=(429, 502, 503, 504),
                      backoff_factor=0.8, allowed_methods=frozenset(["POST"]))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))

    def search(self, start_ms, end_ms, filter_expr, limit=100, offset=0,
               include_extra=False, sort_field="duration_nano"):
        p = api_payload(start_ms, end_ms, filter_expr, offset, limit, include_extra, sort_field)
        try:
            response = self.session.post(self.url + "/api/v5/query_range", json=p,
                                         timeout=(10, 90), allow_redirects=False)
            if response.is_redirect:
                raise RuntimeError(f"SigNoz API 返回重定向 ({response.status_code})，请检查 API URL 和认证代理")
            if self.debug_response:
                path = Path(self.debug_response)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(response.text, encoding="utf-8")
            if response.status_code >= 400:
                raise RuntimeError(f"SigNoz HTTP {response.status_code}: {response.text[:700]}")
            try:
                content = response.json()
            except ValueError as e:
                raise RuntimeError("API 返回的不是 JSON（可能被 SSO/Cloudflare 登录页拦截）") from e
            if isinstance(content, dict) and content.get("status") == "error":
                raise RuntimeError(f"SigNoz 查询失败: {str(content)[:700]}")
            return unpack_rows(content)
        except requests.RequestException as e:
            raise RuntimeError(f"连接 SigNoz 失败: {e}") from e

    def search_pages(self, start_ms, end_ms, expr, max_results, page_size,
                     include_extra=False, sort_field="duration_nano"):
        records, offset, seen = [], 0, set()
        while len(records) < max_results:
            batch = self.search(start_ms, end_ms, expr,
                                limit=min(page_size, max_results-len(records)),
                                offset=offset, include_extra=include_extra,
                                sort_field=sort_field)
            for item in batch:
                ident = (str(val(item, "trace_id", default="")), str(val(item, "span_id", default="")))
                if ident not in seen:
                    seen.add(ident)
                    records.append(item)
            offset += len(batch)
            if len(batch) == 0 or len(batch) < min(page_size, max_results-len(records)+len(batch)):
                break
        return records


def compute_self_times(spans):
    """Exclusive/self time = span interval minus union of its direct child intervals.
    This measures time *not covered by direct child spans*, not pure CPU time.
    """
    children = collections.defaultdict(list)
    for s in spans:
        if s["parent_span_id"] and s["parent_span_id"] != s["span_id"]:
            children[s["parent_span_id"]].append(s)
    for s in spans:
        begin = s["start_ns"]
        end = begin + s["duration_ns"]
        covered = intervals_union_ms([
            (c["start_ns"], c["start_ns"]+c["duration_ns"])
            for c in children.get(s["span_id"], [])], within=(begin, end))
        s["self_ms"] = round(max(0, s["duration_ns"]/1e6-covered), 1)


def trace_subtree(root, spans):
    """Retain root descendants, not unrelated but overlapping branches."""
    by_parent = collections.defaultdict(list)
    for s in spans:
        by_parent[s["parent_span_id"]].append(s)
    chosen, seen = [], set()
    pending = [root]
    while pending:
        s = pending.pop()
        if s["span_id"] in seen:
            continue
        seen.add(s["span_id"])
        chosen.append(s)
        pending.extend(by_parent.get(s["span_id"], []))
    return chosen


def analyze(root, all_spans):
    compute_self_times(all_spans)
    candidates = [s for s in all_spans if s["span_id"] != root["span_id"]]
    total_ms = root["duration_ns"] / 1e6
    start, stop = root["start_ns"], root["start_ns"] + root["duration_ns"]
    groups = collections.defaultdict(list)
    for s in candidates:
        groups[(s["category"], s["name"])].append(s)
    summaries = []
    for (category, operation), items in groups.items():
        summaries.append({
            "category": category, "operation": operation, "count": len(items),
            "sum_ms": round(sum(s["duration_ns"] for s in items)/1e6, 1),
            "wall_union_ms": round(intervals_union_ms([
                (s["start_ns"], s["start_ns"] + s["duration_ns"]) for s in items], within=(start, stop)), 1),
            "max_ms": round(max(s["duration_ns"] for s in items)/1e6, 1),
        })
    summaries.sort(key=lambda x: x["wall_union_ms"], reverse=True)
    gaps = uncovered_intervals(root, candidates, minimum_ms=0)
    missing_ms = sum((b-a) for a,b in gaps)/1e6
    top_gaps = sorted(gaps, key=lambda p:p[1]-p[0], reverse=True)[:5]
    mongo = [s for s in candidates if s["category"] == "MongoDB"]
    mongo_intervals = [(s["start_ns"], s["start_ns"] + s["duration_ns"]) for s in mongo]
    mongo_union = intervals_union_ms(mongo_intervals, within=(start,stop))
    mongo_sum = sum(s["duration_ns"] for s in mongo)/1e6
    mongo_find = [s for s in mongo if "find" in s["name"].lower()]
    n1 = len(mongo_find) >= 10 and mongo_union > 0 and (sum(s["duration_ns"] for s in mongo_find)/1e6) / max(intervals_union_ms([
            (s["start_ns"], s["start_ns"]+s["duration_ns"]) for s in mongo_find], within=(start,stop)), 1) < 1.3
    slowest = max(candidates, key=lambda s:s["duration_ns"], default=None)
    worst_self = max(all_spans, key=lambda s:s["self_ms"], default=None)
    repeated = sorted([g for g in summaries if g["count"] >= 3],
                      key=lambda g:(g["count"], g["wall_union_ms"]), reverse=True)
    return {
        "root": root, "span_count": len(all_spans),
        "total_ms": round(total_ms, 1),
        "slowest": slowest, "worst_self": worst_self, "groups": summaries,
        "mongo_count": len(mongo), "mongo_find_count": len(mongo_find),
        "mongo_sum_ms": round(mongo_sum, 1),
        "mongo_wall_ms": round(mongo_union, 1),
        "uncovered_ms": round(missing_ms, 1),
        "uncovered_pct": round(missing_ms / total_ms *100, 1) if total_ms else 0,
        "top_gaps": [dict(start_offset_ms=round((a-start)/1e6,1), duration_ms=round((b-a)/1e6,1)) for a,b in top_gaps],
        "n_plus_one_suspected": n1,
        "repeated": repeated[:8],
    }


def row_of(a):
    root, slow = a["root"], a["slowest"]
    worst_self = a["worst_self"]
    flags = []
    if a["n_plus_one_suspected"]: flags.append("疑似 N+1/串行重复 MongoDB 查询")
    if a["uncovered_pct"] >= 30: flags.append("大量未覆盖时间，需要补业务Span")
    if not a["span_count"] or a["span_count"] <= 1: flags.append("缺少子Span，无法归因")
    return {
        "timestamp_utc": timestamp_text(root["start_ns"]),
        "service": root["service"], "endpoint": root["name"],
        "http_status": root["status"], "latency_ms": round(root["duration_ns"]/1e6,1),
        "trace_id": root["trace_id"], "span_count": a["span_count"],
        "slowest_child": slow["name"] if slow else "(无子Span)",
        "slowest_child_ms": round(slow["duration_ns"]/1e6,1) if slow else 0,
        "slowest_category": slow["category"] if slow else "unknown",
        "max_self_span": worst_self["name"] if worst_self else "",
        "max_self_ms": worst_self["self_ms"] if worst_self else 0,
        "mongo_count": a["mongo_count"],
        "mongo_find_count": a["mongo_find_count"],
        "mongo_sum_ms": a["mongo_sum_ms"],
        "mongo_wall_ms": a["mongo_wall_ms"],
        "uncovered_ms": a["uncovered_ms"], "uncovered_percent": a["uncovered_pct"],
        "potential_issues": "; ".join(flags) or "结合业务Span继续确认",
    }


def endpoint_summary(reports):
    by_name = collections.defaultdict(list)
    for a in reports:
        by_name[(a["root"]["service"], a["root"]["name"])].append(a)
    result = []
    for (service, endpoint), group in by_name.items():
        slowest = max(group, key=lambda a:a["total_ms"])
        result.append({
            "service":service, "endpoint":endpoint,
            "slow_samples":len(group),
            "slow_sample_avg_ms":round(sum(a["total_ms"] for a in group)/len(group),1),
            "slow_sample_max_ms":round(slowest["total_ms"],1),
            "mongo_calls_avg":round(sum(a["mongo_count"] for a in group)/len(group),1),
            "max_self_ms_avg":round(sum(a["worst_self"]["self_ms"] if a["worst_self"] else 0 for a in group)/len(group),1),
            "example_trace_id":slowest["root"]["trace_id"],
        })
    return sorted(result,key=lambda a:(a["slow_samples"],a["slow_sample_max_ms"]),reverse=True)


def write_csv(dest, rows):
    if not rows:
        return
    with open(dest, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_html(dest: Path, reports):
    rows = [row_of(a) for a in reports]
    grouped = endpoint_summary(reports)
    def td(x): return '<td>'+escape(str(x))+'</td>'
    rollup = "".join("<tr>"+"".join(td(g[x]) for x in ["endpoint","slow_samples","slow_sample_avg_ms","slow_sample_max_ms","mongo_calls_avg","example_trace_id"])+"</tr>" for g in grouped)
    summary = "".join("<tr>"+"".join(td(v) for v in (r["endpoint"], r["latency_ms"], r["span_count"],r["slowest_child"],r["slowest_child_ms"],r["mongo_count"],r["max_self_span"],r["max_self_ms"],r["uncovered_ms"],r["potential_issues"],r["trace_id"]))+"</tr>" for r in rows)
    details = []
    for a in reports:
        root = a["root"]
        groups = "".join("<tr>"+"".join(td(g[k]) for k in ["category", "operation", "count", "sum_ms", "wall_union_ms", "max_ms"])+"</tr>" for g in a["groups"][:15])
        notes = f"总耗时 {a['total_ms']}ms · MongoDB {a['mongo_count']} 次 · 未被Span覆盖 {a['uncovered_ms']}ms ({a['uncovered_pct']}%)"
        details.append(f"<h2>{escape(root['name'])}</h2><p>{escape(root['trace_id'])}</p><p>{escape(notes)}</p><table><thead><tr><th>类型</th><th>Span名称</th><th>次数</th><th>累计耗时(ms)*</th><th>墙钟区间并集(ms)</th><th>最大单次(ms)</th></tr></thead><tbody>{groups}</tbody></table>")
    style = """<style>body{font:14px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:32px auto;max-width:1350px;color:#202937;background:#f5f7fa;padding:0 20px}header{background:#18273e;color:white;padding:24px;border-radius:12px}table{border-collapse:collapse;width:100%;background:white;margin:16px 0 30px;font-size:12px}th,td{padding:10px;border-bottom:1px solid #e6e9ef;text-align:left;vertical-align:top}th{background:#dfe8f5;position:sticky;top:0}tr:hover{background:#f1f6fb}h2{margin-top:36px;color:#254270}p{color:#52647a}header p{color:#d7e2f0}.wrap{overflow:auto}small{color:#52647a}</style>"""
    dest.write_text(f'<!DOCTYPE html><html lang="zh-CN"><meta charset="utf-8"><title>SigNoz 慢请求排查报告</title>{style}<header><h1>SigNoz 慢请求自动诊断报告</h1><p>观察性数据，不等于已验证根因</p></header><h2>慢接口分组汇总（仅慢样本，不代表全部请求）</h2><table><thead><tr><th>接口</th><th>慢样本次数</th><th>慢样本平均(ms)</th><th>最大(ms)</th><th>平均Mongo调用数</th><th>示例Trace</th></tr></thead><tbody>{rollup}</tbody></table><h2>慢接口一览</h2><div class="wrap"><table><thead><tr><th>接口</th><th>耗时(ms)</th><th>Span数</th><th>最慢子Span</th><th>该Span(ms)</th><th>Mongo次数</th><th>未覆盖子Span</th><th>未覆盖子Span耗时(ms)</th><th>根Span未覆盖(ms)</th><th>排查建议</th><th>Trace ID</th></tr></thead><tbody>{summary}</tbody></table></div><small>* 子Span累计时间可因并发、嵌套而超过请求总耗时；“墙钟区间并集”去除了同组Span重叠，组间仍可能重叠。未覆盖时间不等于CPU耗时。</small>{"".join(details)}</html>', encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description="Analyze HTTP server requests above N ms from SigNoz v5 API")
    p.add_argument("--url", default=os.getenv("SIGNOZ_URL", ""))
    p.add_argument("--service", default=os.getenv("SIGNOZ_SERVICE", ""))
    p.add_argument("--hours", type=float, default=24)
    p.add_argument("--threshold-ms", type=float, default=5000)
    p.add_argument("--limit", type=int, default=100, help="max slow HTTP requests (avoid unbounded scans)")
    p.add_argument("--page-size", type=int, default=100)
    p.add_argument("--max-spans", type=int, default=2000, help="max spans fetched per trace")
    p.add_argument("--trace-id", default="", help="analyze one trace directly instead of searching")
    p.add_argument("--out", default="signoz_slow_report")
    p.add_argument("--debug-response", default="", help="save last raw API response for version troubleshooting (may contain sensitive data)")
    args = p.parse_args()
    if not args.url:
        p.error("Set --url or SIGNOZ_URL for your own SigNoz instance")
    if not args.trace_id and not args.service:
        p.error("Set --service or SIGNOZ_SERVICE when searching slow HTTP requests")
    if args.limit < 1 or args.page_size < 1 or args.max_spans < 1 or args.hours <= 0 or args.threshold_ms <= 0:
        p.error("hours / threshold-ms / limit / page-size / max-spans must be positive")
    api_key = os.getenv("SIGNOZ_API_KEY", "").strip()
    if not api_key:
        p.error("请先设置环境变量 SIGNOZ_API_KEY（不要写进脚本或代码仓库）")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    c = Client(args.url, api_key, args.debug_response)
    end_ms = int(time.time() * 1000) - 60_000  # stable near-real-time snapshot
    start_ms = end_ms - int(args.hours * 3600 * 1000)

    try:
        if args.trace_id:
            seeds = [{"trace_id": args.trace_id, "duration_nano": 0, "timestamp": ""}]
        else:
            expr = (f"service.name = '{args.service.replace(chr(39), chr(92)+chr(39))}' "
                    f"AND kind_string = 'Server' AND duration_nano >= {int(args.threshold_ms*1_000_000)}")
            print("正在筛选 HTTP Server 慢请求 ...")
            raw = c.search_pages(start_ms,end_ms, expr, max_results=args.limit,
                                 page_size=args.page_size)
            seeds = [x for x in raw if is_http_server(normalize(x))]
            # raw results may contain other server spans; apply HTTP method check.
            seeds.sort(key=lambda x: ns_of_duration(val(x,"duration_nano", default=0)), reverse=True)
            print(f"慢 HTTP 请求 {len(seeds)} 条（最多扫描 {args.limit} 条 Server Span）")
        reports, all_span_rows = [], []
        done = set()
        for n, item in enumerate(seeds, 1):
            trace_id = str(val(item, "trace_id", default=""))
            if not trace_id:
                print("忽略没有 trace_id 的结果", file=sys.stderr)
                continue
            root_seed = normalize(item)
            # A trace may have several HTTP Server spans. Only analyze selected endpoint root.
            root_id = root_seed["span_id"]
            if not args.trace_id and (trace_id, root_id) in done:
                continue
            done.add((trace_id, root_id))
            ref_ms = (root_seed["start_ns"]//1_000_000) if root_seed["start_ns"] else 0
            detail_start = ref_ms-5*60*1000 if ref_ms else start_ms
            detail_end = ref_ms + max(60_000,root_seed["duration_ns"]//1_000_000)+5*60*1000 if ref_ms else end_ms
            # A finished trace may not be returned if a near-real-time span is not yet ingested.
            print(f"[{n}/{len(seeds)}] 获取 Trace {trace_id[:12]}...", flush=True)
            detail_expr = "trace_id = '" + trace_id.replace("'", "\\'") + "'"
            try:
                raw_spans = c.search_pages(detail_start, detail_end, detail_expr,
                                           max_results=args.max_spans, page_size=min(200,args.page_size),
                                           include_extra=True, sort_field="timestamp")
            except RuntimeError as e:
                print(f"  扩展字段查询失败，退回标准字段: {str(e)[:130]}")
                raw_spans = c.search_pages(detail_start, detail_end, detail_expr,
                                           max_results=args.max_spans, page_size=min(200,args.page_size),
                                           include_extra=False, sort_field="timestamp")
            spans = [normalize(s) for s in raw_spans]
            if not spans:
                print("  没有取到子 Span；保留基础慢请求信息", file=sys.stderr)
                spans = [root_seed] if root_seed["duration_ns"] else []
            root = next((s for s in spans if s["span_id"] and s["span_id"] == root_id), None)
            if not root:
                roots = [s for s in spans if is_http_server(s) and (args.trace_id or s["name"] == root_seed["name"])]
                root = max(roots, key=lambda s:s["duration_ns"], default=None)
            if root is None:
                print("  没有可用的 HTTP Server Span", file=sys.stderr)
                continue
            # Trace ancestry (parent_span_id) determines ownership, not overlap alone.
            scoped = trace_subtree(root, spans)
            a=analyze(root,scoped)
            a["truncated_spans"] = len(raw_spans) >= args.max_spans
            if a["truncated_spans"]:
                print("  警告：Span 已达到 --max-spans 上限，诊断可能不完整")
            reports.append(a)
            for s in scoped:
                all_span_rows.append({
                    "trace_id":trace_id, "span_id":s["span_id"], "parent_span_id":s["parent_span_id"],
                    "name":s["name"], "category":s["category"],"service":s["service"],
                    "start_utc":timestamp_text(s["start_ns"]),"duration_ms":round(s["duration_ns"]/1e6,2),
                    "self_uncovered_ms": s.get("self_ms",0),
                    "kind":s["kind"], "mongo_collection":s["collection"],
                })
        if not reports:
            print("未发现符合条件的可分析 Trace。检查时间范围、服务名、字段名及认证。")
            return 0
        reports.sort(key=lambda a:a["total_ms"],reverse=True)
        summary_rows=[row_of(a) for a in reports]
        write_csv(out/"slow_requests.csv", summary_rows)
        write_csv(out/"endpoint_summary.csv", endpoint_summary(reports))
        write_csv(out/"spans.csv", all_span_rows)
        (out/"analysis.json").write_text(json.dumps([
            {"summary":row_of(a),"groups":a["groups"],"top_gaps":a["top_gaps"],
             "repeated_operations":a["repeated"],"truncated_spans":a["truncated_spans"]}
            for a in reports],indent=2,ensure_ascii=False),encoding="utf-8")
        write_html(out/"report.html",reports)
        (out/"run_metadata.json").write_text(json.dumps({
            "service": args.service,
            "threshold_ms": args.threshold_ms,
            "window_hours": args.hours,
            "query_start_utc": datetime.fromtimestamp(start_ms/1000, tz=timezone.utc).isoformat(),
            "query_end_utc": datetime.fromtimestamp(end_ms/1000, tz=timezone.utc).isoformat(),
            "max_slow_samples": args.limit,
            "collected_slow_samples": len(reports),
            "max_spans_per_trace": args.max_spans,
            "specific_trace_id": args.trace_id or None,
            "potentially_limited": not args.trace_id and len(reports) >= args.limit,
            "not_total_traffic": True,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print("\n慢接口诊断 TOP 10（最多）：")
        for r in summary_rows[:10]:
            print(f"{r['latency_ms']:>9}ms  {r['endpoint'][:53]:53} | Mongo={r['mongo_count']:>3} | "
                  f"未覆盖={r['uncovered_ms']:>7}ms | 最大自耗时Span={r['max_self_span'][:35]} ({r['max_self_ms']}ms)")
        print(f"\n结果已保存到 {out.resolve()}/：report.html, endpoint_summary.csv, slow_requests.csv, spans.csv, analysis.json")
        print("提醒：单次最大Span/重复操作并不自动证明根因；CSV记录是可验证的排查线索。")
    except (RuntimeError,ValueError) as e:
        print(f"错误：{e}",file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
