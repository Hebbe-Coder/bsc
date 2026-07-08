import { skillManager } from './SkillManager';
import { PrdAnalysisSkill } from './skills/PrdAnalysisSkill';
import { ObjectiveExtractionSkill } from './skills/ObjectiveExtractionSkill';
import { KpiExtractionSkill } from './skills/KpiExtractionSkill';
import { ChartGenerationSkill } from './skills/ChartGenerationSkill';
import { PresentationGenerationSkill } from './skills/PresentationGenerationSkill';
import { RiskAssessmentSkill } from './skills/RiskAssessmentSkill';
import { StrategyAnalysisSkill } from './skills/StrategyAnalysisSkill';
import { ReportGenerationSkill } from './skills/ReportGenerationSkill';

skillManager.registerAll([
  PrdAnalysisSkill,
  ObjectiveExtractionSkill,
  KpiExtractionSkill,
  ChartGenerationSkill,
  RiskAssessmentSkill,
  StrategyAnalysisSkill,
  ReportGenerationSkill,
  PresentationGenerationSkill,
]);

export { skillManager };
export { PrdAnalysisSkill, ObjectiveExtractionSkill, KpiExtractionSkill, ChartGenerationSkill, PresentationGenerationSkill, RiskAssessmentSkill, StrategyAnalysisSkill, ReportGenerationSkill };
export type { SkillStatus, SkillConfig, SkillParam, SkillContext, SkillResult, SkillExecution, SkillPlan, SkillTask, SkillConstructor } from './types';
export { BaseSkill } from './types';