"""Black-box behavior and metamorphic tests for job_match."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from resume_agent.tools import JobMatcherTool

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "job_match_cases.yaml"
_BEHAVIOR_DATA = yaml.safe_load(_FIXTURE_PATH.read_text(encoding="utf-8"))
_CASES = _BEHAVIOR_DATA["cases"]
_PARAPHRASE_CASES = _BEHAVIOR_DATA["metamorphic"]["paraphrase_pairs"]
_NOISE_CASES = _BEHAVIOR_DATA["metamorphic"]["noise_tests"]
_BASE_RESUME = _BEHAVIOR_DATA["resume_base"]

_METRIC_MAP = {
    "overall": "match_score",
    "skill": "skill_score",
    "yoe": "yoe_score",
    "location": "location_score",
    "company": "company_experience_score",
}


async def _run_match(tmp_path: Path, resume_text: str, jd_text: str):
    resume_path = tmp_path / "resume.md"
    resume_path.write_text(resume_text, encoding="utf-8")
    matcher = JobMatcherTool(workspace_dir=str(tmp_path))
    result = await matcher.execute(resume_path=str(resume_path), job_text=jd_text)
    assert result.success, f"job_match failed: {result.error}"
    return result


def _assert_bounds(data: dict, expect: dict):
    for key, threshold in expect.items():
        if key.endswith("_min"):
            metric_name = _METRIC_MAP[key[:-4]]
            actual = data[metric_name]
            assert actual >= threshold, f"{metric_name}={actual} < min {threshold}"
        elif key.endswith("_max"):
            metric_name = _METRIC_MAP[key[:-4]]
            actual = data[metric_name]
            assert actual <= threshold, f"{metric_name}={actual} > max {threshold}"
        else:
            raise AssertionError(f"Unsupported expectation key: {key}")


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
@pytest.mark.asyncio
async def test_job_match_behavior_cases(case, tmp_path):
    result = await _run_match(tmp_path, _BASE_RESUME, case["jd"])
    _assert_bounds(result.data, case["expect"])

    # Quick analysis contract should always provide next-step deep analysis hint.
    assert result.data["next_step"]
    assert "deep" in result.data["next_step"].lower()


@pytest.mark.parametrize("case", _PARAPHRASE_CASES, ids=[c["id"] for c in _PARAPHRASE_CASES])
@pytest.mark.asyncio
async def test_job_match_paraphrase_resilience(case, tmp_path):
    result_a = await _run_match(tmp_path, _BASE_RESUME, case["jd_a"])
    result_b = await _run_match(tmp_path, _BASE_RESUME, case["jd_b"])

    overall_delta = abs(result_a.data["match_score"] - result_b.data["match_score"])
    skill_delta = abs(result_a.data["skill_score"] - result_b.data["skill_score"])

    assert (
        overall_delta <= case["expect"]["overall_delta_max"]
    ), f"overall delta too high: {overall_delta} > {case['expect']['overall_delta_max']}"
    assert (
        skill_delta <= case["expect"]["skill_delta_max"]
    ), f"skill delta too high: {skill_delta} > {case['expect']['skill_delta_max']}"


@pytest.mark.parametrize("case", _NOISE_CASES, ids=[c["id"] for c in _NOISE_CASES])
@pytest.mark.asyncio
async def test_job_match_resume_noise_resilience(case, tmp_path):
    clean_result = await _run_match(tmp_path, _BASE_RESUME, case["jd"])
    noisy_resume = _BASE_RESUME + "\n\n" + case["noise_append"]
    noisy_result = await _run_match(tmp_path, noisy_resume, case["jd"])

    overall_delta = abs(clean_result.data["match_score"] - noisy_result.data["match_score"])
    skill_delta = abs(clean_result.data["skill_score"] - noisy_result.data["skill_score"])

    assert (
        overall_delta <= case["expect"]["overall_delta_max"]
    ), f"overall delta too high under noise: {overall_delta} > {case['expect']['overall_delta_max']}"
    assert (
        skill_delta <= case["expect"]["skill_delta_max"]
    ), f"skill delta too high under noise: {skill_delta} > {case['expect']['skill_delta_max']}"
