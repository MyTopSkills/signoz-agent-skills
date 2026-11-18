#!/usr/bin/env python3
"""Install the shared Agent Skill into a target project or user directory."""
import argparse
from pathlib import Path
import shutil

SKILL_NAME = "signoz-fastapi-perf"
SOURCE = Path(__file__).resolve().parents[1] / "skills" / SKILL_NAME


def destination(agent, scope, project):
    if scope == "user":
        base = {"shared": Path.home()/".agents/skills", "codex": Path.home()/".agents/skills",
                "opencode": Path.home()/".config/opencode/skills", "claude": Path.home()/".claude/skills"}[agent]
    else:
        if not project.exists() or not project.is_dir():
            raise ValueError(f"Target project not found: {project}")
        base = project / {"shared": ".agents/skills", "codex": ".agents/skills",
                           "opencode": ".opencode/skills", "claude": ".claude/skills"}[agent]
    return base / SKILL_NAME


def main():
    p = argparse.ArgumentParser(description="Install SigNoz Agent Skill for Codex / OpenCode / Claude")
    p.add_argument("--agent", choices=["shared", "codex", "opencode", "claude"], default="shared")
    p.add_argument("--scope", choices=["project", "user"], default="project")
    p.add_argument("--project", type=Path, default=Path.cwd())
    p.add_argument("--force", action="store_true", help="Replace existing installed skill")
    args = p.parse_args()
    dest = destination(args.agent, args.scope, args.project.expanduser().resolve())
    if dest.exists():
        if not args.force:
            p.error(f"Already exists: {dest}. Use --force to replace")
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, dest)
    print(f"Installed {SKILL_NAME} -> {dest}")
    print("Set SIGNOZ_URL, SIGNOZ_SERVICE and SIGNOZ_API_KEY in your environment.")
    print("Remember to add '.perf-reports/' to your application .gitignore.")


if __name__ == "__main__":
    main()
