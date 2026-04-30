



-- 会话表
CREATE TABLE conversations (
    id            INT                NOT NULL AUTO_INCREMENT COMMENT '主键',
    user_id       INT                NOT NULL                COMMENT '用户 ID',
    session_id    CHAR(18)           NOT NULL DEFAULT        COMMENT '主题 ID',
    title         VARCHAR(255)       NOT NULL DEFAULT        COMMENT '新对话',
    created_at    DATETIME(6)        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME(6)        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_session_id (session_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='会话表';


-- 消息表
CREATE TABLE messages (
    id              INT                NOT NULL AUTO_INCREMENT COMMENT '主键',
    conversation_id INT                NOT NULL                COMMENT '会话 ID',
    role            VARCHAR(20)        NOT NULL                COMMENT '角色',  -- 'system', 'user', 'assistant'
    content         TEXT               NOT NULL,
    status          VARCHAR(20)        NOT NULL                COMMENT '消息状态',  -- 'pending','completed','failed'
    created_at      DATETIME(6)        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME(6)        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_conversation_id (conversation_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='会话表';


CREATE TABLE users (
    id               INT             NOT NULL AUTO_INCREMENT COMMENT '主键',
    username         VARCHAR(64)     NOT NULL                COMMENT '用户名',
    password_hash    VARCHAR(256)    NOT NULL                COMMENT '生成的密码哈希',
    is_superuser     BOOLEAN         NOT NULL                COMMENT '是否为超级管理员',
    is_active        BOOLEAN         NOT NULL                COMMENT '账号是否启用',
    created_at       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login_at    DATETIME(6)     NULL                    COMMENT '最近一次登录时间',

    PRIMARY KEY (id),
    UNIQUE KEY uq_username (username)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='用户表';

