# pylint: disable=line-too-long
"""
模板相关的Invoke模块
"""
import logging
import random
import string
import re
import os
import datetime
import toml

from invoke import task

log = logging.getLogger(__name__)  # pylint: disable=invalid-name

CONFIG_PATH = 'app/config/{config}.toml'
NGINX_PATH = 'deploy/nginx/flask.conf'
MONGO_PATH = 'cmds/{config}_mongodb.txt'
SQL_PATH = 'cmds/{config}_create.sql'
SQLSH_PATH = 'cmds/{config}_createpg.sh'

CONFIG_TYPES = ['development',
                'production',
                'testing']

SETTING_KEYS = ['db_url', 'locale', 'base_prefix', 'timezone', 'mail_server',
                'mail_port', 'mail_username', 'mail_sender', 'mail_passwd',
                'schedule_collection', 'broker_url', 'server_name', 'mongo_db',
                'mongo_user', 'mongo_passwd', 'mongo_host', 'mongo_port']
RANDOM_KEYS = ['secret_key', 'jwt_secret_key', 'passwd_salt']

DEFAULT_VALS = {
    'db_url': 'postgresql://full-stack-flask-admin:full-stack-flask-admin@localhost:5432/full-stack-flask',
    'locale': 'zh_cn',
    'base_prefix': '/api/v1',
    'timezone': 'Asia/Shanghai',
    'schedule_collection': 'full-stack-flask-schedules',
    'mail_server': 'smtp.exmail.qq.com',
    'mail_port': '465',
    'broker_url': 'amqp://',
    'server_name': 'full-flask.net',
    'mongo_db': 'full-stack-flask-admin',
    'mongo_user': 'full-stack-flask-admin',
    'mongo_passwd': 'full-stack-flask-admin',
    'mongo_host': '127.0.0.1',
    'mongo_port': '27017'
}

HELPS = {
    'db_url': 'Postgresql数据库连接地址(SQLAlchemy地址)',
    'locale': '本地化字符串',
    'base_prefix': 'url默认前缀',
    'timezone': '时区',
    'schedule_collection': 'celery调度表表名',
    'mail_server': '邮箱服务地址',
    'mail_username': '邮箱登录用户名',
    'mail_passwd': '邮箱登录密码',
    'mail_sender': '发件人',
    'mail_port': '邮箱服务端口',
    'broker_url': 'celery broker地址',
    'server_name': 'Web服务域名',
    'mongo_db': 'MongoDB数据库名',
    'mongo_user': 'MongoDB数据库用户名',
    'mongo_passwd': 'MongoDB数据库密码',
    'mongo_host': 'MongoDB数据库地址',
    'mongo_port': 'MongoDB数据库端口',
    'secret_key': 'Flask-Login用的密钥字符串',
    'jwt_secret_key': 'Flask-JWT-Extended用的密钥',
    'passwd_salt': '密码加密用盐'
}

EOF_ROLES = "# End Of ROLES"
EOF_PEMISSIONS = "# End Of PERMISSIONS"
EOF_SU = "# End Of SuperUser"
EOF_MAPPING = "# End Of Permissions Mapping"

ADDED_ROLE = ("{model_name}Manager = '{model_name}Manager'\n"
              f"    {EOF_ROLES}"
              )
ADDED_PERMISSIONS = (
    "# {model_name}Manager\n"
    "    {model_name}Add = '{model_name}AddPrivilege'\n"
    "    {model_name}Edit = '{model_name}EditPrivilege'\n"
    "    {model_name}Delete = '{model_name}DeletePrivilege'\n"
    "    {model_name}Query = '{model_name}QueryPrivilege'\n"
    f"    {EOF_PEMISSIONS}"
)
ADDED_SU = (
    "# {module_title}管理\n"
    "        PERMISSIONS.{model_name}Add, PERMISSIONS.{model_name}Delete,\n"
    "        PERMISSIONS.{model_name}Edit, PERMISSIONS.{model_name}Query,\n"
    f"        {EOF_SU}"
)
ADDED_MAPPING = (
    "ROLES.{model_name}Manager: [\n"
    "        PERMISSIONS.{model_name}Add, PERMISSIONS.{model_name}Delete,\n"
    "        PERMISSIONS.{model_name}Edit, PERMISSIONS.{model_name}Query\n"
    "    ],\n"
    f"    {EOF_MAPPING}"
)


def rand_string(strlen=10):
    """生成数字字母特殊字符的随机字符串"""
    password_characters = string.ascii_letters + string.digits + string.punctuation.replace("'", "")
    return ''.join(random.choice(password_characters) for i in range(strlen) if i != "'")


@task
def generate_config(context):
    # pylint: disable=unused-argument
    """
    新建配置内容，根据提示新建配置

    Usage:
    $ invoke app.boilerplates.generate_config
    """
    import jinja2

    from ._utils import rlinput
    from sqlalchemy.engine import url

    config = {}

    setted_default = False

    for config_type in CONFIG_TYPES:
        log.info(f"正在为{config_type}环境设置配置....")
        if not setted_default:
            for key in SETTING_KEYS:
                if key in DEFAULT_VALS:
                    value = rlinput(
                        '请设置 %s (%s) \n(默认 %s): \n' % (key, HELPS[key], DEFAULT_VALS[key]),
                        DEFAULT_VALS[key]
                    )
                    config[key] = value if value else DEFAULT_VALS[key]
                else:
                    config[key] = input('请设置 %s (%s): ' % (key, HELPS[key]))
                print()
            for key in RANDOM_KEYS:
                rand_str = rand_string(30)
                value = rlinput(
                    '请设置 %s (%s) \n(默认 %s): \n' % (key, HELPS[key], rand_str),
                    rand_str
                )
                config[key] = value if value else rand_str
                print()

            _default_config = config.copy()
            setted_default = True
        else:
            for key in _default_config:
                value = rlinput(
                    '请设置 %s (%s) \n(默认 %s): \n' % (key, HELPS[key], _default_config[key]),
                    _default_config[key]
                )
                config[key] = value if value else _default_config[key]
                print()

        # Genrate configuration
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader('tasks/app/templates/configurations/')
        )

        log.info("正在生成配置...")
        for template_name, conf_path in [
                ['config.template', CONFIG_PATH],
                ['nginx.template', NGINX_PATH],
                ['mongodb.template', MONGO_PATH]
        ]:
            template = env.get_template(template_name)
            template.stream(
                **config
            ).dump('%s' % conf_path.format(config=config_type))

        log.info("正在生成Postgresql初始化指令...")
        for template_name, conf_path in [
                ['sql.template', SQL_PATH],
                ['sql-sh.template', SQLSH_PATH]
        ]:
            template = env.get_template(template_name)
            u = url.make_url(config['db_url'])
            template.stream(
                db_username=u.username,
                db_password=u.password,
                db_name=u.database
            ).dump('%s' % conf_path.format(config=config_type))

        print()

    log.info("配置文件生成完毕.")


@task
def crud_module(context, module_name='', module_name_singular='',
                module_title='', description=''):
    # pylint: disable=unused-argument
    """
    新建一个增删改查模块
    来源：frol/flask-restplus-server-example

    用法:
    $ inv app.boilerplates.crud-module --module-name=articles \
                --module-name-singular=article \
                --description=文章的增删改查API \
                --module_title=文章

    """
    try:
        import jinja2
    except ImportError:
        log.critical("缺少jinja2模块，请通过`pip install jinja2`安装")
        return

    if not module_name:
        log.critical("请提供模块名")
        return

    if not re.match('^[a-zA-Z0-9_]+$', module_name):
        log.critical(
            "模块名中包含特殊字符"
            "([a-zA-Z0-9_]+)"
        )
        return

    if not module_name_singular:
        module_name_singular = module_name[:-1]

    module_path = 'app/modules/%s' % module_name
    admin_views_path = 'app/admin/views'

    if not module_title:
        module_title = " ".join(
            [word.capitalize()
                for word in module_name.split('_')
             ]
        )

    model_name = "".join(
        [word.capitalize()
            for word in module_name_singular.split('_')
         ]
    )

    if os.path.exists(module_path):
        log.critical('模块 `%s` 已存在.', module_name)
        return

    os.makedirs(module_path)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader('tasks/app/templates/crud_module')
    )

    # 从pyproject中获取author
    pyproject = toml.load('pyproject.toml')
    authors = pyproject['tool']['poetry']['authors']
    author = authors[0] if authors else ''

    for template_file in (
        '__init__',
        'models',
        'params',
        'resources',
        'schemas',
    ):
        template = env.get_template('%s.py.template' % template_file)
        template.stream(
            module_name=module_name,
            module_name_singular=module_name_singular,
            module_title=module_title,
            module_namespace=module_name.replace('_', '-'),
            model_name=model_name,
            description=description,
            year=datetime.date.today().year,
            author=author
        ).dump(
            '%s/%s.py' % (module_path, template_file)
        )

    # 生成admin模板
    log.info("生成admin的views模板中...")
    template = env.get_template('adminview.py.template')
    template.stream(
        module_name=module_name,
        module_title=module_title,
        model_name=model_name,
        year=datetime.date.today().year,
        author=author
    ).dump(
        '%s/%s.py' % (admin_views_path, module_name)
    )
    log.info(f'{admin_views_path}/{module_name}.py已生成，请在app/admin/register.py中添加相关信息。')

    permissions_adder(context, model_name=model_name, module_title=module_title)

    log.info("模块 `%s` 创建成功.", module_name)


@task
def permissions_adder(context, model_name='', module_title=''):
    # pylint: disable=unused-argument
    """
    为权限文件新增新的模块权限

    用法:
    $ inv app.boilerplates.permissions-adder --module-name=articles \
                --module_title=文章

    """

    added_role = ADDED_ROLE.format(model_name=model_name)
    added_permissions = ADDED_PERMISSIONS.format(model_name=model_name)
    added_su = ADDED_SU.format(model_name=model_name, module_title=module_title)
    added_mapping = ADDED_MAPPING.format(model_name=model_name)

    with open('app/modules/auth/permissions.py') as f:
        text = f.read()

    for orig, subs in [
            [EOF_ROLES, added_role],
            [EOF_PEMISSIONS, added_permissions],
            [EOF_SU, added_su],
            [EOF_MAPPING, added_mapping]
    ]:
        text = text.replace(orig, subs)

    with open('app/modules/auth/permissions.new.py', 'w') as f:
        f.write(text)

    log.info("新权限文件 `%s` 生成成功.\n", 'app/modules/auth/permissions.new.py')
    log.info("请编辑后替换旧权限文件，并执行`invoke app.db.update-app-permissions`")
