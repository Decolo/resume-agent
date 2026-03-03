"""Run black-box behavior evaluation for job_match."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import yaml

from resume_agent.tools import JobMatcherTool

METRIC_MAP = {
    "overall": "match_score",
    "skill": "skill_score",
    "yoe": "yoe_score",
    "location": "location_score",
    "company": "company_experience_score",
}


async def _run_match(matcher: JobMatcherTool, workspace: Path, resume_text: str, jd_text: str):
    resume_path = workspace / "resume.md"
    resume_path.write_text(resume_text, encoding="utf-8")
    return await matcher.execute(resume_path=str(resume_path), job_text=jd_text)


def _check_bounds(data: Dict[str, Any], expect: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    for key, threshold in expect.items():
        if key.endswith("_min"):
            metric_name = METRIC_MAP[key[:-4]]
            actual = data[metric_name]
            if actual < threshold:
                failures.append(f"{metric_name}={actual} < min {threshold}")
        elif key.endswith("_max"):
            metric_name = METRIC_MAP[key[:-4]]
            actual = data[metric_name]
            if actual > threshold:
                failures.append(f"{metric_name}={actual} > max {threshold}")
        else:
            failures.append(f"unsupported expectation key: {key}")
    return failures


async def evaluate(fixtures_path: Path) -> Dict[str, Any]:
    payload = yaml.safe_load(fixtures_path.read_text(encoding="utf-8"))
    resume_base: str = payload["resume_base"]
    cases = payload["cases"]
    paraphrase_pairs = payload["metamorphic"]["paraphrase_pairs"]
    noise_tests = payload["metamorphic"]["noise_tests"]

    report: Dict[str, Any] = {"cases": [], "metamorphic": [], "summary": {}}
    total = 0
    passed = 0

    with tempfile.TemporaryDirectory(prefix="jobmatch_eval_") as tmp_dir:
        workspace = Path(tmp_dir)
        matcher = JobMatcherTool(workspace_dir=str(workspace))

        for case in cases:
            total += 1
            result = await _run_match(matcher, workspace, resume_base, case["jd"])
            failures: List[str] = []
            if not result.success:
                failures = [f"tool_error: {result.error}"]
            else:
                failures = _check_bounds(result.data, case["expect"])
            ok = len(failures) == 0
            if ok:
                passed += 1
            report["cases"].append(
                {
                    "id": case["id"],
                    "ok": ok,
                    "failures": failures,
                    "scores": result.data if result.success else {},
                }
            )

        for case in paraphrase_pairs:
            total += 1
            res_a = await _run_match(matcher, workspace, resume_base, case["jd_a"])
            res_b = await _run_match(matcher, workspace, resume_base, case["jd_b"])
            failures = []
            if not res_a.success or not res_b.success:
                failures.append(f"tool_error: jd_a={res_a.error}, jd_b={res_b.error}")
            else:
                overall_delta = abs(res_a.data["match_score"] - res_b.data["match_score"])
                skill_delta = abs(res_a.data["skill_score"] - res_b.data["skill_score"])
                if overall_delta > case["expect"]["overall_delta_max"]:
                    failures.append(f"overall_delta={overall_delta} > max {case['expect']['overall_delta_max']}")
                if skill_delta > case["expect"]["skill_delta_max"]:
                    failures.append(f"skill_delta={skill_delta} > max {case['expect']['skill_delta_max']}")
            ok = len(failures) == 0
            if ok:
                passed += 1
            report["metamorphic"].append({"id": case["id"], "kind": "paraphrase", "ok": ok, "failures": failures})

        for case in noise_tests:
            total += 1
            clean = await _run_match(matcher, workspace, resume_base, case["jd"])
            noisy = await _run_match(matcher, workspace, resume_base + "\n\n" + case["noise_append"], case["jd"])
            failures = []
            if not clean.success or not noisy.success:
                failures.append(f"tool_error: clean={clean.error}, noisy={noisy.error}")
            else:
                overall_delta = abs(clean.data["match_score"] - noisy.data["match_score"])
                skill_delta = abs(clean.data["skill_score"] - noisy.data["skill_score"])
                if overall_delta > case["expect"]["overall_delta_max"]:
                    failures.append(f"overall_delta={overall_delta} > max {case['expect']['overall_delta_max']}")
                if skill_delta > case["expect"]["skill_delta_max"]:
                    failures.append(f"skill_delta={skill_delta} > max {case['expect']['skill_delta_max']}")
            ok = len(failures) == 0
            if ok:
                passed += 1
            report["metamorphic"].append({"id": case["id"], "kind": "noise", "ok": ok, "failures": failures})

    report["summary"] = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0.0,
    }
    return report


def _print_human(report: Dict[str, Any]) -> None:
    print("Job Match Behavior Evaluation")
    print("=" * 40)
    for case in report["cases"]:
        status = "PASS" if case["ok"] else "FAIL"
        print(f"[{status}] case:{case['id']}")
        for failure in case["failures"]:
            print(f"  - {failure}")
    for case in report["metamorphic"]:
        status = "PASS" if case["ok"] else "FAIL"
        print(f"[{status}] {case['kind']}:{case['id']}")
        for failure in case["failures"]:
            print(f"  - {failure}")

    summary = report["summary"]
    print("-" * 40)
    print(
        f"Summary: {summary['passed']}/{summary['total']} passed "
        f"({summary['pass_rate']:.1%}), failed={summary['failed']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run behavior eval for job_match")
    parser.add_argument(
        "--fixtures",
        default="tests/behavior/fixtures/job_match_cases.yaml",
        help="Path to fixture YAML file",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any behavior check fails",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON report instead of human-readable output",
    )
    args = parser.parse_args()

    report = asyncio.run(evaluate(Path(args.fixtures)))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)

    if args.strict and report["summary"]["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
