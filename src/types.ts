export type Role = 'system' | 'user' | 'assistant' | 'observation';
export interface Message { role: Role; content: string; }

export type ToolName = 'read_file' | 'write_file' | 'list_dir' | 'run_shell' | 'run_tests' | 'finish';
export interface Action { tool: ToolName; args: Record<string, any>; }

export interface Observation {
  ok: boolean;
  stdout?: string;
  stderr?: string;
  exitCode?: number;
  error?: string;
  content?: string;
}

export type ErrorType = 'assertion' | 'syntax' | 'other';
export interface Feedback {
  errorType: ErrorType;
  failedTests: string[];
  assertion?: { file: string; line: number; snippet: string };
  evidence: string;
  hint: string;
}

export type Severity = 'none' | 'low' | 'high';
export interface GuardrailVerdict { severity: Severity; reasons: string[]; }

// 会话状态：由 AgentLoop 维护、传递给 Guardrail 做状态感知评估。
// lastDenied=true 表示上一轮动作刚被用户拒绝（Deny）。
export interface SessionState { lastDenied: boolean; }

export interface ApprovalRequest { id: string; action: Action; reasons: string[]; }
export interface ApprovalDecision { decision: 'approve' | 'deny'; reason: string; }
export type Approval = ApprovalRequest & Partial<ApprovalDecision>;
export type LoopState = 'RUNNING' | 'APPROVAL_PENDING' | 'EXECUTING' | 'HALTED';

export type EventType = 'action' | 'observation' | 'approval_request' | 'approval_decision' | 'halt';
export interface Event { id: number; type: EventType; payload: any; iter: number; }
