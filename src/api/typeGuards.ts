import { BusinessSystem, CompileResult, Skill, SkillExecutionResponse } from './bscApi';

export const isObject = (obj: unknown): obj is Record<string, unknown> => {
  return typeof obj === 'object' && obj !== null;
};

export const isString = (value: unknown): value is string => {
  return typeof value === 'string';
};

export const isNumber = (value: unknown): value is number => {
  return typeof value === 'number' && !isNaN(value);
};

export const isArray = <T>(value: unknown, predicate: (item: unknown) => item is T): value is T[] => {
  return Array.isArray(value) && value.every(predicate);
};

export const isSkill = (obj: unknown): obj is Skill => {
  if (!isObject(obj)) return false;
  const skill = obj as unknown as Skill;
  return isString(skill.id) && isString(skill.name) && isString(skill.description);
};

export const isSkillsArray = (value: unknown): value is Skill[] => {
  return isArray(value, isSkill);
};

export const isObjective = (obj: unknown): obj is BusinessSystem['objectives'][number] => {
  if (!isObject(obj)) return false;
  const objective = obj as BusinessSystem['objectives'][number];
  return isString(objective.objective) && isString(objective.target);
};

export const isRole = (obj: unknown): obj is BusinessSystem['roles'][number] => {
  if (!isObject(obj)) return false;
  const role = obj as BusinessSystem['roles'][number];
  return isString(role.role) && isArray(role.responsibilities, isString);
};

export const isWorkflowStep = (obj: unknown): obj is BusinessSystem['workflow'][number] => {
  if (!isObject(obj)) return false;
  const step = obj as BusinessSystem['workflow'][number];
  return isNumber(step.step) && isString(step.name) && isString(step.action);
};

export const isMetric = (obj: unknown): obj is BusinessSystem['metrics'][number] => {
  if (!isObject(obj)) return false;
  const metric = obj as BusinessSystem['metrics'][number];
  return isString(metric.name) && isString(metric.formula) && isString(metric.target);
};

export const isRisk = (obj: unknown): obj is BusinessSystem['risks'][number] => {
  if (!isObject(obj)) return false;
  const risk = obj as BusinessSystem['risks'][number];
  return isString(risk.risk) && isString(risk.severity) && isString(risk.mitigation);
};

type GrowthOpportunity = BusinessSystem['strategy']['growth_opportunities'] extends Array<infer T> ? T : never;
type Recommendation = BusinessSystem['optimization']['recommendations'] extends Array<infer T> ? T : never;
type ReportSection = BusinessSystem['report']['sections'] extends Array<infer T> ? T : never;

export const isGrowthOpportunity = (obj: unknown): obj is GrowthOpportunity => {
  if (!isObject(obj)) return false;
  const opportunity = obj as GrowthOpportunity;
  return isString(opportunity.opportunity) && isString(opportunity.potential);
};

export const isRecommendation = (obj: unknown): obj is Recommendation => {
  if (!isObject(obj)) return false;
  const recommendation = obj as Recommendation;
  return isString(recommendation.recommendation) && isString(recommendation.impact);
};

export const isReportSection = (obj: unknown): obj is ReportSection => {
  if (!isObject(obj)) return false;
  const section = obj as ReportSection;
  return isString(section.title) && isString(section.content);
};

export const isBusinessSystem = (obj: unknown): obj is BusinessSystem => {
  if (!isObject(obj)) return false;
  
  const system = obj as unknown as BusinessSystem;
  
  const hasRequiredFields = isString(system.business_domain);
  
  const hasValidObjectives = !system.objectives || isArray(system.objectives, isObjective);
  const hasValidRoles = !system.roles || isArray(system.roles, isRole);
  const hasValidWorkflow = !system.workflow || isArray(system.workflow, isWorkflowStep);
  const hasValidMetrics = !system.metrics || isArray(system.metrics, isMetric);
  const hasValidRisks = !system.risks || isArray(system.risks, isRisk);
  
  const hasValidStrategy = !system.strategy || (
    !system.strategy.growth_opportunities || isArray(system.strategy.growth_opportunities, isGrowthOpportunity)
  );
  
  const hasValidOptimization = !system.optimization || (
    !system.optimization.recommendations || isArray(system.optimization.recommendations, isRecommendation)
  );
  
  const hasValidReport = !system.report || (
    (!system.report.title || isString(system.report.title)) &&
    (!system.report.executive_summary || isString(system.report.executive_summary)) &&
    (!system.report.sections || isArray(system.report.sections, isReportSection))
  );
  
  return hasRequiredFields && hasValidObjectives && hasValidRoles && hasValidWorkflow && 
         hasValidMetrics && hasValidRisks && hasValidStrategy && hasValidOptimization && hasValidReport;
};

export const isSkillExecutionResponse = (obj: unknown): obj is SkillExecutionResponse => {
  if (!isObject(obj)) return false;
  
  const response = obj as unknown as SkillExecutionResponse;
  
  return isString(response.execution_id) && isString(response.status);
};

type Stage = CompileResult['pipeline']['stages'][number];

export const isStage = (obj: unknown): obj is Stage => {
  if (!isObject(obj)) return false;
  
  const stage = obj as unknown as Stage;
  
  return isString(stage.agent) && isString(stage.key) && isString(stage.display) && 
         isString(stage.status) && isNumber(stage.duration_ms);
};

export const isCompileResult = (obj: unknown): obj is CompileResult => {
  if (!isObject(obj)) return false;
  
  const result = obj as unknown as CompileResult;
  
  const hasValidBusinessSystem = isBusinessSystem(result.business_system);
  
  const hasValidPipeline = isObject(result.pipeline) && 
    isArray(result.pipeline.stages, isStage) && 
    isNumber(result.pipeline.total_ms);
  
  const hasValidSummary = isString(result.summary);
  
  return hasValidBusinessSystem && hasValidPipeline && hasValidSummary;
};

export const validateBusinessSystem = (obj: unknown): BusinessSystem => {
  if (!isBusinessSystem(obj)) {
    throw new Error('Invalid BusinessSystem structure');
  }
  return obj;
};

export const validateCompileResult = (obj: unknown): CompileResult => {
  if (!isCompileResult(obj)) {
    throw new Error('Invalid CompileResult structure');
  }
  return obj;
};

export const validateSkillExecutionResponse = (obj: unknown): SkillExecutionResponse => {
  if (!isSkillExecutionResponse(obj)) {
    throw new Error('Invalid SkillExecutionResponse structure');
  }
  return obj;
};