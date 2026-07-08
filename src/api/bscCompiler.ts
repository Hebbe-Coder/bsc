import { BusinessSystem, bscApi } from './bscApi';
import { convertBusinessSystemToPresentation } from '../utils/bscConverter';
import { Presentation } from '../types';

export type BscStage = 'business_understanding' | 'sop' | 'risk' | 'strategy' | 'optimization' | 'composer';

export interface BscProgress {
  stage: BscStage | 'initializing' | 'completed';
  status: 'running' | 'completed' | 'failed';
  progress: number;
  message: string;
}

export type BscProgressCallback = (progress: BscProgress) => void;

export const bscCompiler = {
  async compile(
    input: string,
    onProgress?: BscProgressCallback
  ): Promise<Presentation> {
    if (onProgress) {
      onProgress({ stage: 'initializing', status: 'running', progress: 0, message: '正在初始化BSC Pipeline...' });
    }

    try {
      if (onProgress) {
        onProgress({ stage: 'business_understanding', status: 'running', progress: 10, message: '正在分析业务理解...' });
      }

      const result = await bscApi.compile(input, 'builtin_content_moderation');

      const stages = result.pipeline?.stages || [];
      const totalStages = stages.length;

      for (let i = 0; i < stages.length; i++) {
        const stage = stages[i];
        if (onProgress) {
          const progress = Math.round(10 + (i + 1) * (80 / totalStages));
          onProgress({ 
            stage: stage.key as BscStage, 
            status: stage.status as 'running' | 'completed', 
            progress, 
            message: `正在执行: ${stage.display}` 
          });
        }
      }

      if (onProgress) {
        onProgress({ stage: 'completed', status: 'completed', progress: 100, message: 'BSC Pipeline执行完成，正在生成演示文稿...' });
      }

      const businessSystem = result.business_system;
      const presentation = convertBusinessSystemToPresentation(businessSystem, 'business');

      return presentation;
    } catch (error) {
      if (onProgress) {
        onProgress({ stage: 'completed', status: 'failed', progress: 0, message: error instanceof Error ? error.message : '编译失败' });
      }
      throw error;
    }
  },

  async compileSync(
    input: string,
    onProgress?: BscProgressCallback
  ): Promise<Presentation> {
    if (onProgress) {
      onProgress({ stage: 'initializing', status: 'running', progress: 0, message: '正在初始化BSC Pipeline（同步模式）...' });
    }

    try {
      const stages: Array<{ key: BscStage; display: string }> = [
        { key: 'business_understanding', display: '业务理解' },
        { key: 'sop', display: '流程设计' },
        { key: 'risk', display: '风险分析' },
        { key: 'strategy', display: '战略分析' },
        { key: 'optimization', display: '优化建议' },
        { key: 'composer', display: '结果组装' },
      ];

      for (let i = 0; i < stages.length; i++) {
        const stage = stages[i];
        if (onProgress) {
          const progress = Math.round(10 + (i + 1) * (80 / stages.length));
          onProgress({ 
            stage: stage.key, 
            status: 'running', 
            progress, 
            message: `正在执行: ${stage.display}...` 
          });
        }

        try {
          await bscApi.executeStage({ input, stage_key: stage.key });
        } catch {
              console.warn(`Stage ${stage.key} failed with sync mode, trying compile...`);
            }
      }

      if (onProgress) {
        onProgress({ stage: 'completed', status: 'running', progress: 90, message: '正在获取编译结果...' });
      }

      const result = await bscApi.compileSync(input);
      const businessSystem = result.business_system;

      if (onProgress) {
        onProgress({ stage: 'completed', status: 'completed', progress: 100, message: '正在生成演示文稿...' });
      }

      const presentation = convertBusinessSystemToPresentation(businessSystem, 'business');
      return presentation;
    } catch (error) {
      if (onProgress) {
        onProgress({ stage: 'completed', status: 'failed', progress: 0, message: error instanceof Error ? error.message : '编译失败' });
      }
      throw error;
    }
  },

  async getBusinessSystem(input: string): Promise<BusinessSystem> {
    const result = await bscApi.compile(input);
    return result.business_system;
  },

  async export(
    businessSystem: BusinessSystem,
    outputTypes: string[] = ['html', 'json']
  ) {
    return await bscApi.export(businessSystem, outputTypes);
  },

  async health(): Promise<{ pipeline: string; llm: { status: string; provider: string } }> {
    return await bscApi.health();
  },

  async stages(): Promise<Array<{ key: string; agent: string; display: string; type: string }>> {
    return await bscApi.stages();
  },
};

export default bscCompiler;