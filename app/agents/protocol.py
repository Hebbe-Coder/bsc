﻿﻿﻿﻿﻿﻿﻿﻿﻿'''Protocol types for BSC Studio agents - unified interface.

This module now uses the unified agent interface from unified_agent.py
to ensure type consistency across the entire system.
'''
from typing import Any, Optional, List

from app.agents.unified_agent import UnifiedBaseAgent, AgentContext, AgentResult


class BaseAgent(UnifiedBaseAgent):
    '''Base agent class for BSC Studio v3 specialized agents.
    
    Subclasses override on_generate and/or on_analyze.
    
    This class now inherits from UnifiedBaseAgent for type consistency.
    '''
    name: str = 'base'
    description: str = ''
    capabilities: list[str] = []

    def on_generate(self, ctx: AgentContext, **params) -> dict:
        raise NotImplementedError

    def on_analyze(self, ctx: AgentContext, **params) -> dict:
        raise NotImplementedError

    def run(self, ctx: AgentContext, **params) -> AgentResult:
        try:
            if 'generate' in self.capabilities:
                data = self.on_generate(ctx, **params)
            else:
                data = self.on_analyze(ctx, **params)
            return self._wrap_result(data)
        except Exception as e:
            return self._wrap_result({}, status="failed", error=str(e))
