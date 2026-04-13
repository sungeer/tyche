-- ============================================================
-- Hostess 数据库表结构
-- 数据库版本：MySQL 8.4.8
-- 字符集：utf8mb4
-- 排序规则：utf8mb4_unicode_ci
-- 时间字段均使用 UTC 时区，精度为毫秒（DATETIME(3)）
-- 软删除字段 deleted_at：0 表示未删除，大于 0 表示删除时的毫秒时间戳
-- ============================================================


-- ============================================================
-- 一、会话域
-- ============================================================

-- 对话会话表
-- 每个用户可同时拥有多个会话，会话记录多轮对话的上下文
CREATE TABLE agent_session (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT          COMMENT '自增主键',
    session_id      VARCHAR(64)         NOT NULL                         COMMENT '会话唯一标识（UUID hex）',
    user_id         BIGINT UNSIGNED     NOT NULL                         COMMENT '关联用户表的主键',
    status          VARCHAR(16)         NOT NULL DEFAULT 'active'        COMMENT '会话状态：active=活跃，closed=已关闭',
    turn_count      INT UNSIGNED        NOT NULL DEFAULT 0               COMMENT '累计对话轮次数',
    last_active_at  DATETIME(3)         NOT NULL                         COMMENT '最后活跃时间（UTC）',
    created_at      DATETIME(3)         NOT NULL                         COMMENT '创建时间（UTC）',
    updated_at      DATETIME(3)         NOT NULL                         COMMENT '最后更新时间（UTC）',
    deleted_at      BIGINT UNSIGNED     NOT NULL DEFAULT 0               COMMENT '软删除时间戳（毫秒）；0 表示未删除',
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_session_session_id (session_id),
    KEY idx_agent_session_user_id (user_id)
) COMMENT '对话会话表';


-- 对话消息表
-- 记录每一轮对话的用户输入与助手回复，仅追加写入，不修改
CREATE TABLE agent_message (
    id          BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT          COMMENT '自增主键',
    session_id  VARCHAR(64)         NOT NULL                         COMMENT '关联 agent_session 表的 session_id',
    turn_id     VARCHAR(64)         NOT NULL                         COMMENT '本轮对话唯一 ID，一个 turn_id 对应一问一答',
    role        VARCHAR(16)         NOT NULL                         COMMENT '消息角色：user=用户，assistant=助手',
    content     TEXT                NOT NULL                         COMMENT '消息正文内容',
    created_at  DATETIME(3)         NOT NULL                         COMMENT '消息写入时间（UTC）',
    PRIMARY KEY (id),
    KEY idx_agent_message_session_id (session_id),
    KEY idx_agent_message_turn_id (turn_id)
) COMMENT '对话消息表（仅追加）';


-- ============================================================
-- 二、合规与审计域
-- ============================================================

-- 审计日志表
-- 每一轮完整对话结束后写入一条，包含脱敏的合规数据与防篡改哈希
-- 仅追加写入，禁止更新
CREATE TABLE agent_audit_log (
    id                  BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT          COMMENT '自增主键',
    run_id              VARCHAR(64)         NOT NULL                         COMMENT '请求级追踪 ID（来自 HTTP 中间件）',
    session_id          VARCHAR(64)         NOT NULL                         COMMENT '关联 agent_session 表的 session_id',
    turn_id             VARCHAR(64)         NOT NULL                         COMMENT '本轮对话唯一 ID',
    user_id             BIGINT UNSIGNED     NOT NULL                         COMMENT '关联用户表的主键',
    operator_role       JSON                NOT NULL                         COMMENT '操作人角色列表（JSON 数组）',
    intent_category     VARCHAR(64)         NOT NULL DEFAULT ''              COMMENT '识别出的用户意图类别',
    intent_confidence   FLOAT               NOT NULL DEFAULT 0               COMMENT '意图识别置信度（0~1）',
    skills_called       JSON                NOT NULL                         COMMENT '调用的 Skill 摘要列表（含状态和耗时，不含业务数据）',
    compliance_events   JSON                NOT NULL                         COMMENT '合规检查事件列表（已 PII 脱敏）',
    node_durations      JSON                NOT NULL                         COMMENT '各节点耗时（毫秒）键值对',
    llm_token_usage     JSON                NOT NULL                         COMMENT 'LLM Token 用量汇总',
    final_status        VARCHAR(32)         NOT NULL DEFAULT ''              COMMENT '流程最终状态（completed/rejected/failed/pending_review 等）',
    content_hash        VARCHAR(64)         NOT NULL DEFAULT ''              COMMENT 'SHA-256 防篡改哈希，对除本字段外的所有字段计算',
    created_at          DATETIME(3)         NOT NULL                         COMMENT '审计日志写入时间（UTC）',
    PRIMARY KEY (id),
    KEY idx_agent_audit_log_turn_id (turn_id),
    KEY idx_agent_audit_log_user_id (user_id),
    KEY idx_agent_audit_log_created_at (created_at)
) COMMENT '审计日志表（仅追加，防篡改）';


-- 人工审核任务表
-- 触发人工审核规则时创建，记录审核流程的完整状态
CREATE TABLE agent_review_task (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT          COMMENT '自增主键',
    task_id         VARCHAR(64)         NOT NULL                         COMMENT '审核任务唯一标识（UUID hex）',
    turn_id         VARCHAR(64)         NOT NULL                         COMMENT '关联发起审核的对话轮次 ID',
    user_id         BIGINT UNSIGNED     NOT NULL                         COMMENT '关联发起操作的用户主键',
    assigned_role   VARCHAR(64)         NOT NULL DEFAULT ''              COMMENT '指定处理该任务的角色名称',
    assigned_to     BIGINT UNSIGNED     NOT NULL DEFAULT 0               COMMENT '实际接单的审核人 ID；0 表示未指定',
    trigger_rule    VARCHAR(64)         NOT NULL DEFAULT ''              COMMENT '触发审核的规则 ID',
    trigger_detail  VARCHAR(512)        NOT NULL DEFAULT ''              COMMENT '触发原因的详细说明',
    status          VARCHAR(32)         NOT NULL DEFAULT 'pending'       COMMENT '审核状态：pending=待审，approved=通过，rejected=驳回，escalated=上升',
    reviewer_note   VARCHAR(2048)       NOT NULL DEFAULT ''              COMMENT '审核人备注或驳回原因',
    sla_deadline    DATETIME(3)         NOT NULL                         COMMENT '审核 SLA 截止时间（UTC），超时应告警',
    reviewed_at     DATETIME(3)         NULL     DEFAULT NULL            COMMENT '审核人完成操作的时间（UTC）；NULL 表示尚未审核',
    created_at      DATETIME(3)         NOT NULL                         COMMENT '任务创建时间（UTC）',
    updated_at      DATETIME(3)         NOT NULL                         COMMENT '任务最后更新时间（UTC）',
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_review_task_task_id (task_id),
    KEY idx_agent_review_task_turn_id (turn_id),
    KEY idx_agent_review_task_user_id (user_id),
    KEY idx_agent_review_task_assigned_role (assigned_role),
    KEY idx_agent_review_task_status (status)
) COMMENT '人工审核任务表';


-- AgentState 快照表
-- 触发人工审核时将整个 AgentState 序列化存入，审核通过后反序列化恢复执行
CREATE TABLE agent_state_snapshot (
    id          BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT          COMMENT '自增主键',
    task_id     VARCHAR(64)         NOT NULL                         COMMENT '关联 agent_review_task 表的 task_id',
    state_json  MEDIUMTEXT          NOT NULL                         COMMENT '序列化的 AgentState JSON，用于审核通过后从 Node3 恢复执行',
    created_at  DATETIME(3)         NOT NULL                         COMMENT '快照创建时间（UTC）',
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_state_snapshot_task_id (task_id)
) COMMENT 'AgentState 快照表（人工审核恢复用）';


-- ============================================================
-- 三、工作流追踪域（事件溯源）
-- ============================================================

-- 工作流执行记录表
-- 每次 Pipeline 执行（每一轮对话）对应一条记录
-- 在 Pipeline 启动时写入，结束时更新最终状态
-- 配合 workflow_step 表可完整还原任意一次执行的全过程
CREATE TABLE workflow_run (
    id          BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT          COMMENT '自增主键',
    turn_id     VARCHAR(64)         NOT NULL                         COMMENT '本轮对话唯一 ID，与 agent_message.turn_id 对应',
    session_id  VARCHAR(64)         NOT NULL                         COMMENT '关联 agent_session 表的 session_id',
    user_id     BIGINT UNSIGNED     NOT NULL                         COMMENT '关联用户表的主键',
    status      VARCHAR(32)         NOT NULL DEFAULT 'running'       COMMENT '流程状态：running=执行中，completed=正常完成，rejected=合规拒绝，failed=异常失败，short_circuited=意图短路，pending_review=待人工审核',
    created_at  DATETIME(3)         NOT NULL                         COMMENT 'Pipeline 启动时间（UTC）',
    updated_at  DATETIME(3)         NOT NULL                         COMMENT '状态最后更新时间（UTC）',
    PRIMARY KEY (id),
    UNIQUE KEY uk_workflow_run_turn_id (turn_id),
    KEY idx_workflow_run_user_id (user_id),
    KEY idx_workflow_run_status (status),
    KEY idx_workflow_run_created_at (created_at)
) COMMENT '工作流执行记录表；每轮对话一条，记录整体生命周期';


-- 工作流节点步骤表
-- 每个节点执行完成后立即写入一条，记录该节点的关键输出与耗时
-- 进程崩溃时，已写入的步骤不丢失，可还原崩溃前的执行进度
CREATE TABLE workflow_step (
    id           BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT          COMMENT '自增主键',
    turn_id      VARCHAR(64)         NOT NULL                         COMMENT '关联 workflow_run 表的 turn_id',
    node_name    VARCHAR(64)         NOT NULL                         COMMENT '节点名称（如 node1_intent_parser）',
    status       VARCHAR(16)         NOT NULL                         COMMENT '节点执行结果：ok=成功，failed=异常',
    output_json  MEDIUMTEXT          NOT NULL                         COMMENT '节点关键输出的结构化快照（JSON）；不存储业务敏感数据，只记录决策信息',
    error_msg    VARCHAR(1024)       NOT NULL DEFAULT ''              COMMENT '节点执行失败时的错误信息；成功时为空字符串',
    started_at   DATETIME(3)         NOT NULL                         COMMENT '节点开始执行时间（UTC）',
    ended_at     DATETIME(3)         NOT NULL                         COMMENT '节点结束执行时间（UTC）',
    duration_ms  INT UNSIGNED        NOT NULL DEFAULT 0               COMMENT '节点执行耗时（毫秒）',
    PRIMARY KEY (id),
    KEY idx_workflow_step_turn_id (turn_id)
) COMMENT '工作流节点步骤表；每个节点完成后实时写入，支持逐步追溯与对账';
