-- ================================================================
-- RAG 问答系统 —— 完整建表 DDL
-- MySQL 8.0+，使用 InnoDB + utf8mb4
-- 建表顺序：permissions → roles → roles_permissions →
--           users → knowledge_bases → user_profiles →
--           kb_members → query_histories
-- ================================================================

-- ----------------------------------------------------------------
-- 1. permissions  权限表
-- ----------------------------------------------------------------
CREATE TABLE `permissions` (
    `id`          INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name`        VARCHAR(50)  NOT NULL                COMMENT '权限标识符，全大写下划线风格，如 QUERY、UPLOAD',
    `description` VARCHAR(200)     NULL                COMMENT '权限用途描述',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_permissions_name` (`name`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='权限表';


-- ----------------------------------------------------------------
-- 2. roles  用户角色表
-- ----------------------------------------------------------------
CREATE TABLE `roles` (
    `id`          INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name`        VARCHAR(30)  NOT NULL                COMMENT '角色名称，如 Member、Contributor',
    `description` VARCHAR(200)     NULL                COMMENT '角色定位说明',
    `is_default`  TINYINT(1)   NOT NULL DEFAULT 0      COMMENT '是否为新用户注册的默认角色（全表只能有一条为 1）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_roles_name` (`name`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='用户角色表';


-- ----------------------------------------------------------------
-- 3. roles_permissions  角色-权限多对多关联表
-- ----------------------------------------------------------------
CREATE TABLE `roles_permissions` (
    `role_id`       INT NOT NULL COMMENT '角色 ID',
    `permission_id` INT NOT NULL COMMENT '权限 ID',
    PRIMARY KEY (`role_id`, `permission_id`),
    CONSTRAINT `fk_rp_role`
        FOREIGN KEY (`role_id`)       REFERENCES `roles`(`id`)       ON DELETE CASCADE,
    CONSTRAINT `fk_rp_permission`
        FOREIGN KEY (`permission_id`) REFERENCES `permissions`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='角色权限关联表';


-- ----------------------------------------------------------------
-- 4. users  用户账号表
--    注意：此时不含对 knowledge_bases 的 FK，后者依赖 users
--    user_profiles 中的 default_kb_id FK 在第 6 张表中声明
-- ----------------------------------------------------------------
CREATE TABLE `users` (
    `id`            INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
    `username`      VARCHAR(64)  NOT NULL                COMMENT '用户名，全局唯一',
    `email`         VARCHAR(254) NOT NULL                COMMENT '邮箱地址，全局唯一',
    `password_hash` VARCHAR(256) NOT NULL                COMMENT '生成的密码哈希',
    `is_active`     TINYINT(1)   NOT NULL DEFAULT 1      COMMENT '账号是否启用，0 等同于封号',
    `is_confirmed`  TINYINT(1)   NOT NULL DEFAULT 0      COMMENT '邮箱是否已验证',
    `storage_quota` BIGINT       NOT NULL DEFAULT 1073741824 COMMENT '存储上限（字节），默认 1 GB；-1 表示无限制',
    `storage_used`  BIGINT       NOT NULL DEFAULT 0      COMMENT '已使用存储空间（字节）',
    `role_id`       INT              NULL                COMMENT '所属角色，NULL 表示未分配',
    `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP                    COMMENT '账号创建时间',
    `updated_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    `last_login_at` DATETIME         NULL                COMMENT '最近一次登录时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_users_username` (`username`),
    UNIQUE KEY `uq_users_email`    (`email`),
    KEY `idx_users_role_id`        (`role_id`),
    CONSTRAINT `fk_users_role`
        FOREIGN KEY (`role_id`) REFERENCES `roles`(`id`) ON DELETE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='用户账号表';


-- ----------------------------------------------------------------
-- 5. knowledge_bases  知识库表
-- ----------------------------------------------------------------
CREATE TABLE `knowledge_bases` (
    `id`          INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name`        VARCHAR(100) NOT NULL                COMMENT '知识库名称',
    `description` TEXT             NULL                COMMENT '知识库描述',
    `owner_id`    INT          NOT NULL                COMMENT '所有者用户 ID',
    `is_public`   TINYINT(1)   NOT NULL DEFAULT 0      COMMENT '是否公开发布：0=私有，1=全平台可查询',
    `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP                    COMMENT '创建时间',
    `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    PRIMARY KEY (`id`),
    KEY `idx_kb_owner_id` (`owner_id`),
    KEY `idx_kb_is_public` (`is_public`),
    CONSTRAINT `fk_kb_owner`
        FOREIGN KEY (`owner_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='知识库表';


-- ----------------------------------------------------------------
-- 6. user_profiles  用户个性化偏好表（与权限完全解耦）
-- ----------------------------------------------------------------
CREATE TABLE `user_profiles` (
    `user_id`          INT      NOT NULL            COMMENT '关联用户 ID（1:1）',
    `preferred_kb_ids` JSON         NULL            COMMENT '用户置顶的知识库 ID 列表，如 [3, 7, 12]，首屏优先展示',
    `domain_tags`      JSON         NULL            COMMENT '领域标签列表，如 ["法律","合规"]，RAG 检索时作 metadata filter',
    `default_kb_id`    INT          NULL            COMMENT '默认问答知识库，未设置则要求用户主动选择',
    `extra`            JSON         NULL            COMMENT '预留扩展字段（UI 主题、界面语言、LLM 温度偏好等）',
    `updated_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    PRIMARY KEY (`user_id`),
    KEY `idx_up_default_kb_id` (`default_kb_id`),
    CONSTRAINT `fk_up_user`
        FOREIGN KEY (`user_id`)       REFERENCES `users`(`id`)           ON DELETE CASCADE,
    CONSTRAINT `fk_up_default_kb`
        FOREIGN KEY (`default_kb_id`) REFERENCES `knowledge_bases`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='用户个性化偏好表';


-- ----------------------------------------------------------------
-- 7. kb_members  知识库定向共享成员表
-- ----------------------------------------------------------------
CREATE TABLE `kb_members` (
    `id`         INT         NOT NULL AUTO_INCREMENT COMMENT '主键',
    `kb_id`      INT         NOT NULL                COMMENT '知识库 ID',
    `user_id`    INT         NOT NULL                COMMENT '被授权用户 ID',
    `permission` VARCHAR(20) NOT NULL DEFAULT 'READ' COMMENT '共享权限：READ=只读查询 / WRITE=可上传文档',
    `granted_at` DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '授权时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_kb_member` (`kb_id`, `user_id`)   COMMENT '同一用户在同一知识库只能有一条授权记录',
    KEY `idx_kbm_user_id` (`user_id`),
    CONSTRAINT `fk_kbm_kb`
        FOREIGN KEY (`kb_id`)   REFERENCES `knowledge_bases`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_kbm_user`
        FOREIGN KEY (`user_id`) REFERENCES `users`(`id`)           ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='知识库共享成员表（定向授权）';


-- ----------------------------------------------------------------
-- 8. query_histories  问答历史记录表
--    使用 BIGINT 主键，预留百亿级记录空间
-- ----------------------------------------------------------------
CREATE TABLE `query_histories` (
    `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    `user_id`     INT          NOT NULL                COMMENT '发起查询的用户 ID',
    `kb_id`       INT              NULL                COMMENT '查询的知识库 ID，NULL 表示跨库全局查询',
    `question`    TEXT         NOT NULL                COMMENT '用户的原始提问',
    `answer`      LONGTEXT         NULL                COMMENT 'LLM 生成的回答',
    `source_docs` JSON             NULL                COMMENT '召回的参考文档片段（chunk_id、来源文件名、相似度分等）',
    `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '问答发生时间',
    PRIMARY KEY (`id`),
    KEY `idx_qh_user_id`    (`user_id`),
    KEY `idx_qh_kb_id`      (`kb_id`),
    KEY `idx_qh_created_at` (`created_at`),
    CONSTRAINT `fk_qh_user`
        FOREIGN KEY (`user_id`) REFERENCES `users`(`id`)           ON DELETE CASCADE,
    CONSTRAINT `fk_qh_kb`
        FOREIGN KEY (`kb_id`)   REFERENCES `knowledge_bases`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='问答历史记录表';


-- ================================================================
-- 初始化数据：内置权限与角色
-- 执行一次即可，支持幂等（INSERT IGNORE）
-- ================================================================

-- 权限
INSERT IGNORE INTO `permissions` (`name`, `description`) VALUES
    ('QUERY',         '向所有可访问的知识库发起 RAG 检索问答'),
    ('UPLOAD',        '向知识库上传文档'),
    ('CREATE_KB',     '创建新知识库'),
    ('MANAGE_OWN_KB', '管理自己名下的知识库（改名/删文档/删知识库）'),
    ('SHARE_KB',      '将自己的知识库定向共享给指定用户'),
    ('PUBLISH_KB',    '将自己的知识库设为平台公开，所有人可查询'),
    ('MODERATE',      '下架或编辑他人发布的公开知识库内容'),
    ('MANAGE_USERS',  '查看、禁用、修改用户账号及角色分配'),
    ('ADMINISTER',    '系统级配置与全量数据操作');

-- 角色
INSERT IGNORE INTO `roles` (`name`, `description`, `is_default`) VALUES
    ('Viewer',        '访客/受限用户：仅可查询被共享或公开的知识库，无法创建或上传', 0),
    ('Member',        '普通成员（默认角色）：拥有完整的私有知识库体验',              1),
    ('Contributor',   '内容贡献者：在 Member 基础上，可共享或公开发布知识库',        0),
    ('Moderator',     '内容管理员：可治理平台公开知识库中的不当内容',                0),
    ('Administrator', '系统管理员：拥有全部权限',                                    0);

-- 角色-权限绑定
INSERT IGNORE INTO `roles_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id
FROM `roles` r
JOIN `permissions` p
    ON  r.name = 'Viewer'
    AND p.name IN ('QUERY');

INSERT IGNORE INTO `roles_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id
FROM `roles` r
JOIN `permissions` p
    ON  r.name = 'Member'
    AND p.name IN ('QUERY','UPLOAD','CREATE_KB','MANAGE_OWN_KB');

INSERT IGNORE INTO `roles_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id
FROM `roles` r
JOIN `permissions` p
    ON  r.name = 'Contributor'
    AND p.name IN ('QUERY','UPLOAD','CREATE_KB','MANAGE_OWN_KB','SHARE_KB','PUBLISH_KB');

INSERT IGNORE INTO `roles_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id
FROM `roles` r
JOIN `permissions` p
    ON  r.name = 'Moderator'
    AND p.name IN ('QUERY','UPLOAD','CREATE_KB','MANAGE_OWN_KB','SHARE_KB','PUBLISH_KB','MODERATE');

INSERT IGNORE INTO `roles_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id
FROM `roles` r
JOIN `permissions` p
    ON  r.name = 'Administrator'
    AND p.name IN ('QUERY','UPLOAD','CREATE_KB','MANAGE_OWN_KB','SHARE_KB','PUBLISH_KB','MODERATE','MANAGE_USERS','ADMINISTER');


-- ----------------------------------------------------------------
-- 1. conversations  多轮对话会话表
-- ----------------------------------------------------------------
CREATE TABLE `conversations` (
    `id`             BIGINT       NOT NULL AUTO_INCREMENT  COMMENT '主键',
    `user_id`        INT          NOT NULL                 COMMENT '发起会话的用户 ID',
    `kb_id`          INT              NULL                 COMMENT '会话默认知识库，可被单轮覆盖；NULL 表示跨库全局问答',
    `title`          VARCHAR(200)     NULL                 COMMENT '会话标题：首轮提问后由系统截取前 50 字或由 LLM 生成',
    `summary`        TEXT             NULL                 COMMENT '滚动压缩的历史摘要：早期轮次超出窗口后由后台任务压缩写入，LLM 读此字段而非全量历史',
    `status`         TINYINT(1)   NOT NULL DEFAULT 1       COMMENT '会话状态：1=活跃，0=已归档（软删除）',
    `turn_count`     INT          NOT NULL DEFAULT 0       COMMENT '轮次数缓存，避免 COUNT(*) 全扫；每次 INSERT conversation_turns 后同步 +1',
    `last_active_at` DATETIME         NULL                 COMMENT '最后一条消息的时间，用于会话列表排序',
    `created_at`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP                     COMMENT '会话创建时间',
    `updated_at`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    PRIMARY KEY (`id`),
    KEY `idx_conv_user_status`  (`user_id`, `status`),
    KEY `idx_conv_last_active`  (`user_id`, `last_active_at` DESC),
    KEY `idx_conv_kb_id`        (`kb_id`),
    CONSTRAINT `fk_conv_user`
        FOREIGN KEY (`user_id`) REFERENCES `users`(`id`)           ON DELETE CASCADE,
    CONSTRAINT `fk_conv_kb`
        FOREIGN KEY (`kb_id`)   REFERENCES `knowledge_bases`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='多轮对话会话表';


-- ----------------------------------------------------------------
-- 2. conversation_turns  单轮问答记录表（原 query_histories 重构）
-- ----------------------------------------------------------------
CREATE TABLE `conversation_turns` (
    `id`                BIGINT       NOT NULL AUTO_INCREMENT  COMMENT '主键',
    `conversation_id`   BIGINT       NOT NULL                 COMMENT '所属会话 ID',
    `user_id`           INT          NOT NULL                 COMMENT '冗余用户 ID，避免高频查询时 JOIN conversations',
    `kb_id`             INT              NULL                 COMMENT '本轮实际使用的知识库，覆盖会话默认值；NULL 则继承 conversations.kb_id',
    `turn_index`        SMALLINT     NOT NULL                 COMMENT '本会话内的轮次序号，从 1 开始，用于滑动窗口截取上下文',
    `question`          TEXT         NOT NULL                 COMMENT '用户原始提问',
    `answer`            LONGTEXT         NULL                 COMMENT 'LLM 生成的回答；NULL 表示正在生成或生成失败',
    `source_docs`       JSON             NULL                 COMMENT '本轮 RAG 召回的文档片段元信息（chunk_id、文件名、相似度分、摘录文本）',
    `prompt_tokens`     INT              NULL                 COMMENT '本轮送入 LLM 的 token 数（含系统提示 + 摘要 + 上下文窗口 + 当前问题）',
    `completion_tokens` INT              NULL                 COMMENT '本轮 LLM 输出的 token 数',
    `latency_ms`        INT              NULL                 COMMENT 'LLM 首 token 响应耗时（毫秒），用于性能监控',
    `is_regenerated`    TINYINT(1)   NOT NULL DEFAULT 0       COMMENT '是否为用户点击"重新生成"后产生的回答（同一 turn_index 可能有多次，取最新一条）',
    `created_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '本轮问答时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_turn` (`conversation_id`, `turn_index`, `is_regenerated`),
    KEY `idx_ct_user_id`    (`user_id`),
    KEY `idx_ct_kb_id`      (`kb_id`),
    KEY `idx_ct_created_at` (`created_at`),
    CONSTRAINT `fk_ct_conversation`
        FOREIGN KEY (`conversation_id`) REFERENCES `conversations`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ct_user`
        FOREIGN KEY (`user_id`)         REFERENCES `users`(`id`)           ON DELETE CASCADE,
    CONSTRAINT `fk_ct_kb`
        FOREIGN KEY (`kb_id`)           REFERENCES `knowledge_bases`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='多轮对话单轮问答记录表';


-- ----------------------------------------------------------------
-- 1. kb_documents  文档表 记录上传了哪些原始文件
-- ----------------------------------------------------------------
CREATE TABLE `kb_documents` (
    `id`          INT          NOT NULL AUTO_INCREMENT,
    `user_id`     INT          NOT NULL COMMENT '关联用户 ID',
    `kb_id`       INT          NOT NULL COMMENT '归属知识库',
    `filename`    VARCHAR(255) NOT NULL COMMENT '原始文件名',
    `file_path`   VARCHAR(500) NOT NULL COMMENT '存储路径或对象存储 key',
    `status`      TINYINT      NOT NULL DEFAULT 0 COMMENT '0=处理中 1=就绪 2=失败',
    `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    CONSTRAINT `fk_doc_kb` FOREIGN KEY (`kb_id`) REFERENCES `knowledge_bases`(`id`) ON DELETE CASCADE
);


-- ----------------------------------------------------------------
-- 2. kb_chunks  切片表 存储切割后的文本块及向量索引信息（RAG 的核心）
-- ----------------------------------------------------------------
CREATE TABLE `kb_chunks` (
    `id`           INT          NOT NULL AUTO_INCREMENT,
    `kb_id`        INT          NOT NULL COMMENT '归属知识库（冗余存，方便直接按库检索）',
    `document_id`  INT          NOT NULL COMMENT '归属文档',
    `content`      TEXT         NOT NULL COMMENT '切片后落地的文本',
    `vector_id`    VARCHAR(100)     NULL COMMENT '向量数据库中对应的 ID（如 Milvus/Qdrant）',
    `chunk_index`  INT          NOT NULL COMMENT '在文档中的顺序',
    `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    CONSTRAINT `fk_chunk_doc` FOREIGN KEY (`document_id`) REFERENCES `kb_documents`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_chunk_kb`  FOREIGN KEY (`kb_id`)       REFERENCES `knowledge_bases`(`id`) ON DELETE CASCADE
);


