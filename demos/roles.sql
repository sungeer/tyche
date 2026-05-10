

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

