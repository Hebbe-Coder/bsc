import { SkillConfig, SkillContext, SkillExecution, SkillConstructor, BaseSkill, SkillPlan, SkillTask, SkillStatus, ProgressCallback } from './types';
import { API_BASE } from '../config';
import { apiFetch } from '../api/fetchWrapper';

class SkillManager {
  private skills: Map<string, SkillConstructor> = new Map();
  private executions: Map<string, SkillExecution> = new Map();
  private listeners: Map<string, Set<(execution: SkillExecution) => void>> = new Map();

  register(skill: SkillConstructor): void {
    const config = new skill().getConfig();
    this.skills.set(config.id, skill);
  }

  registerAll(skills: SkillConstructor[]): void {
    skills.forEach(skill => this.register(skill));
  }

  getSkill(id: string): SkillConstructor | undefined {
    return this.skills.get(id);
  }

  getSkillInstance(id: string): BaseSkill | undefined {
    const SkillClass = this.skills.get(id);
    return SkillClass ? new SkillClass() : undefined;
  }

  getAllSkills(): SkillConfig[] {
    return Array.from(this.skills.values()).map(SkillClass => new SkillClass().getConfig());
  }

  getSkillsByCategory(category: SkillConfig['category']): SkillConfig[] {
    return this.getAllSkills().filter(skill => skill.category === category);
  }

  async executeSkill(
    skillId: string, 
    context: SkillContext, 
    params?: Record<string, any>,
    onProgress?: ProgressCallback
  ): Promise<SkillExecution> {
    const executionId = `exec-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const execution: SkillExecution = {
      id: executionId,
      skillId,
      status: 'running',
      progress: 0,
      context,
      startTime: new Date(),
    };

    this.executions.set(executionId, execution);
    this.notifyListeners(executionId, execution);

    try {
      const skillInstance = this.getSkillInstance(skillId);
      if (!skillInstance) {
        throw new Error(`Skill ${skillId} not found`);
      }

      if (onProgress) {
        onProgress(10, 'running', 'Initializing skill execution...');
      }

      const result = await skillInstance.execute(context, params);
      execution.status = result.success ? 'completed' : 'failed';
      execution.progress = 100;
      execution.result = result;
      execution.endTime = new Date();

      if (onProgress) {
        onProgress(100, execution.status, result.success ? 'Execution completed' : 'Execution failed');
      }
    } catch (error) {
      execution.status = 'failed';
      execution.progress = 0;
      execution.result = {
        success: false,
        data: {},
        error: error instanceof Error ? error.message : 'Unknown error',
        logs: [],
      };
      execution.endTime = new Date();

      if (onProgress) {
        onProgress(0, 'failed', execution.result.error);
      }
    }

    this.executions.set(executionId, execution);
    this.notifyListeners(executionId, execution);
    return execution;
  }

  async executePlan(
    plan: SkillPlan,
    onProgress?: (taskId: string, progress: number, status: string) => void
  ): Promise<SkillPlan> {
    plan.status = 'executing';
    
    const completedTasks = new Set<string>();
    const executingTasks = new Set<string>();

    while (completedTasks.size < plan.tasks.length) {
      for (const task of plan.tasks) {
        if (task.status === 'completed' || task.status === 'running') continue;
        
        const allDependenciesMet = task.dependsOn.every(depId => completedTasks.has(depId));
        
        if (allDependenciesMet && !executingTasks.has(task.id)) {
          task.status = 'running';
          executingTasks.add(task.id);

          if (onProgress) {
            onProgress(task.id, 0, 'running');
          }

          try {
            const context: SkillContext = {};
            task.dependsOn.forEach(depId => {
              const depTask = plan.tasks.find(t => t.id === depId);
              if (depTask?.result?.success) {
                Object.assign(context, depTask.result.data);
              }
            });

            const execution = await this.executeSkill(
              task.skillId, 
              context, 
              task.params,
              (progress, status) => {
                if (onProgress) {
                  onProgress(task.id, progress, status);
                }
              }
            );
            task.result = execution.result;
            task.status = execution.status;
            
            if (execution.status === 'completed') {
              completedTasks.add(task.id);
            }
          } catch (error) {
            task.status = 'failed';
            task.result = {
              success: false,
              data: {},
              error: error instanceof Error ? error.message : 'Unknown error',
              logs: [],
            };
            plan.status = 'failed';
            
            if (onProgress) {
              onProgress(task.id, 0, 'failed');
            }
            
            return plan;
          } finally {
            executingTasks.delete(task.id);
          }
        }
      }

      await new Promise(resolve => setTimeout(resolve, 100));
    }

    plan.status = 'completed';
    return plan;
  }

  subscribe(executionId: string, callback: (execution: SkillExecution) => void): () => void {
    if (!this.listeners.has(executionId)) {
      this.listeners.set(executionId, new Set());
    }
    this.listeners.get(executionId)!.add(callback);

    return () => {
      const callbacks = this.listeners.get(executionId);
      if (callbacks) {
        callbacks.delete(callback);
        if (callbacks.size === 0) {
          this.listeners.delete(executionId);
        }
      }
    };
  }

  private notifyListeners(executionId: string, execution: SkillExecution): void {
    const callbacks = this.listeners.get(executionId);
    if (callbacks) {
      callbacks.forEach(callback => callback(execution));
    }
  }

  getExecution(executionId: string): SkillExecution | undefined {
    return this.executions.get(executionId);
  }

  createPlan(tasks: Omit<SkillTask, 'status' | 'result'>[]): SkillPlan {
    return {
      id: `plan-${Date.now()}`,
      tasks: tasks.map(task => ({ ...task, status: 'idle' as SkillStatus })),
      status: 'draft',
      createdAt: new Date(),
    };
  }

  async fetchSkillsFromBackend(): Promise<void> {
    try {
      const response = await apiFetch(`${API_BASE}/api/skill/list`);
      const skills = await response.json();

      console.log('Fetched skills from backend:', skills.length);
    } catch (error) {
      console.error('Failed to fetch skills from backend:', error);
    }
  }
}

export const skillManager = new SkillManager();

export default skillManager;
