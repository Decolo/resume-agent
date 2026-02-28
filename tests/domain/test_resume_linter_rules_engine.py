"""Rules-engine focused tests for production resume linter interface."""

from __future__ import annotations

import pytest

from resume_agent.tools import ResumeLinterTool


@pytest.fixture
def linter(tmp_path):
    return ResumeLinterTool(workspace_dir=str(tmp_path))


def _write_resume(tmp_path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class TestScopedRules:
    @pytest.mark.asyncio
    async def test_metrics_rule_ignores_non_experience_sections(self, linter, tmp_path):
        project_bullets = "\n".join([f"- Built helper script {i}" for i in range(1, 11)])
        content = f"""# Jane
jane@example.com | +1 555-123-4567 | linkedin.com/in/jane

## Experience
- Led migration of payment service, reduced failure rate by 22%
- Implemented deployment automation, cut release time by 35%

## Projects
{project_bullets}

## Education
BS Computer Science

## Skills
- Python
"""
        path = _write_resume(tmp_path, "scope_projects.md", content)
        result = await linter.execute(path=str(path), lang="en")
        assert result.success
        kw_issues = result.data["sections"]["keywords"]["issues"]
        assert not any("rule:low_metrics_density" in issue for issue in kw_issues)

    @pytest.mark.asyncio
    async def test_scope_rules_skip_when_experience_missing(self, linter, tmp_path):
        content = """# Person
person@example.com | +1 555-123-4567 | linkedin.com/in/person

## Projects
- Responsible for backend support and internal maintenance
- Worked with team on improvements

## Education
BS Computer Science

## Skills
- Python
"""
        path = _write_resume(tmp_path, "no_experience.md", content)
        result = await linter.execute(path=str(path), lang="en")
        assert result.success
        kw_issues = result.data["sections"]["keywords"]["issues"]
        assert not any("rule:low_metrics_density" in issue for issue in kw_issues)
        assert not any("rule:bullet_starts_with_verb" in issue for issue in kw_issues)


class TestLanguageRouting:
    @pytest.mark.asyncio
    async def test_auto_route_zh_reports_language_metadata(self, linter, tmp_path):
        content = """# 张三
邮箱: zhangsan@example.com | 电话: 138-0000-0000 | LinkedIn: linkedin.com/in/zhangsan

## 工作经历
- 主导订单系统重构，将接口平均响应时间降低 35%。
- 负责数据看板优化，运营处理时长下降 18%。

## 教育
计算机科学 学士

## 技能
- Python
"""
        path = _write_resume(tmp_path, "zh_auto.md", content)
        result = await linter.execute(path=str(path), lang="auto")
        assert result.success
        assert any("Language route: zh" in s for s in result.data["suggestions"])

    @pytest.mark.asyncio
    async def test_unsupported_lang_falls_back_without_failure(self, linter, tmp_path):
        content = """# Alex
alex@example.com | +1 555-222-3333 | linkedin.com/in/alex

## Experience
- Led backend migration and reduced errors by 15%

## Education
BS Computer Science

## Skills
- Python
"""
        path = _write_resume(tmp_path, "fallback_lang.md", content)
        result = await linter.execute(path=str(path), lang="fr")
        assert result.success
        assert any("fallback:unsupported-manual" in s for s in result.data["suggestions"])


class TestSpacyVerbRule:
    @pytest.fixture
    def has_spacy_model(self):
        try:
            import spacy

            spacy.load("en_core_web_sm")
            return True
        except Exception:
            return False

    @pytest.mark.asyncio
    async def test_non_verb_start_bullet_triggers_rule(self, linter, tmp_path, has_spacy_model):
        if not has_spacy_model:
            pytest.skip("spaCy model en_core_web_sm not available")
        content = """# Riley
riley@example.com | +1 555-333-7777 | linkedin.com/in/riley

## Experience
- Responsible for backend support and documentation
- Responsible for release process coordination

## Education
BS Computer Science

## Skills
- Python
"""
        path = _write_resume(tmp_path, "verb_bad.md", content)
        result = await linter.execute(path=str(path), lang="en")
        assert result.success
        kw_issues = result.data["sections"]["keywords"]["issues"]
        assert any("rule:bullet_starts_with_verb" in issue for issue in kw_issues)

    @pytest.mark.asyncio
    async def test_action_verb_start_bullets_do_not_trigger_rule(self, linter, tmp_path, has_spacy_model):
        if not has_spacy_model:
            pytest.skip("spaCy model en_core_web_sm not available")
        content = """# Riley
riley@example.com | +1 555-333-7777 | linkedin.com/in/riley

## Experience
- Led backend migration and reduced defects by 20%
- Implemented test automation and cut release time by 30%

## Education
BS Computer Science

## Skills
- Python
"""
        path = _write_resume(tmp_path, "verb_good.md", content)
        result = await linter.execute(path=str(path), lang="en")
        assert result.success
        kw_issues = result.data["sections"]["keywords"]["issues"]
        assert not any("rule:bullet_starts_with_verb" in issue for issue in kw_issues)


class TestChineseSupport:
    @pytest.mark.asyncio
    async def test_required_sections_recognized_for_chinese_headers(self, linter, tmp_path):
        content = """# 张三
邮箱: zhangsan@example.com | 电话: 138-0000-0000 | LinkedIn: linkedin.com/in/zhangsan

## 工作经历
- 主导订单系统重构，将接口平均响应时间降低 35%。
- 推动发布流程优化，将上线失败率从 5.2% 降至 1.1%。

## 教育
计算机科学 学士

## 技能
- Python
"""
        path = _write_resume(tmp_path, "zh_required_sections.md", content)
        result = await linter.execute(path=str(path), lang="zh")
        assert result.success
        comp_issues = [i.lower() for i in result.data["sections"]["completeness"]["issues"]]
        assert not any("missing 'experience'" in i for i in comp_issues)
        assert not any("missing 'education'" in i for i in comp_issues)
        assert not any("missing 'skills'" in i for i in comp_issues)

    @pytest.mark.asyncio
    async def test_chinese_job_description_does_not_force_empty_keyword_penalty(self, linter, tmp_path):
        resume = """# 张三
邮箱: zhangsan@example.com | 电话: 138-0000-0000 | LinkedIn: linkedin.com/in/zhangsan

## 工作经历
- 负责数据平台建设，提升处理效率 30%。
- 优化任务调度流程，将失败率降低 20%。

## 教育
计算机科学 学士

## 技能
- Python
"""
        jd = "需要熟悉数据平台建设、任务调度优化与流程改进，能够推动稳定性提升。"
        path = _write_resume(tmp_path, "zh_jd.md", resume)
        result = await linter.execute(path=str(path), job_description=jd, lang="zh")
        assert result.success
        kw_issues = result.data["sections"]["keywords"]["issues"]
        assert not any("consider adding:" in i and i.strip().endswith(":") for i in kw_issues)

    @pytest.mark.asyncio
    async def test_non_english_mode_skips_english_action_verb_heuristic(self, linter, tmp_path):
        content = """# 李四
邮箱: lisi@example.com | 电话: 138-0000-1111 | LinkedIn: linkedin.com/in/lisi

## 工作经历
- 负责客户系统改造，处理时长下降 25%。
- 主导监控告警优化，故障恢复时间缩短 18%。

## 教育
软件工程 学士

## 技能
- Python
"""
        path = _write_resume(tmp_path, "zh_skip_english_verb.md", content)
        result = await linter.execute(path=str(path), lang="zh")
        assert result.success
        kw_issues = result.data["sections"]["keywords"]["issues"]
        assert not any("few action verbs found in experience bullets" in i.lower() for i in kw_issues)
