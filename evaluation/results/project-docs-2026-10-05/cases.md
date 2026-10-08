# 三个实际开发集案例

模型答案未运行；下面是参考要点与真实检索上下文，不能当作生成结果。

## Q02：父块回补补齐证据

问题：第一次启动后端，要先启动哪些配套服务？用什么命令？（top_k=5）

参考要点：在项目根目录启动 PostgreSQL 和 Mailcatcher；docker compose up -d db mailcatcher

### 纯向量 + 子块

完整覆盖：False；上下文：1652 字符；模型答案：未运行或生成失败（见 answers 逐题状态）

**[1] development.md / FastAPI Project - Development / Full Stack with Docker Compose**

`````markdown
**Note**: The first time you start the stack, it might take a minute for all the services to be ready. To monitor it, use `docker compose logs`, or `docker compose logs backend` for the backend service.

`````

**[2] development.md / FastAPI Project - Development / Pre-commits and code linting / Install prek to run automatically**

`````markdown
runs automatically before each commit.

Using `uv`, you could do it with (make sure you are inside `backend` folder):

```bash
❯ uv run prek install -f
prek installed at `../.git/hooks/pre-commit`
```

`````

**[3] backend/README.md / FastAPI Project - Backend / Local Development**

`````markdown
e
$ docker compose up -d db mailcatcher
```

Then, from `./backend/`, install the dependencies, prepare the database, and start the development server:

```console
$ uv sync
$ uv run bash scripts/prestart.sh

`````

**[4] development.md / FastAPI Project - Development / Pre-commits and code linting / Install prek to run automatically**

`````markdown
rt of the dependencies of the project.

After having the `prek` tool installed and available, you need to "install" it in the local repository, so that it runs automatically before each commit.


`````

**[5] deployment-docker-compose.md / FastAPI Project - Docker Compose Deployment / Deploy with GitHub Actions / Install a Self-Hosted Runner**

`````markdown
See GitHub's guides for [adding a self-hosted runner](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners) and [configuring the runner as a service](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application?
`````

### 混合检索 + 子块

完整覆盖：False；上下文：1652 字符；模型答案：未运行或生成失败（见 answers 逐题状态）

**[1] development.md / FastAPI Project - Development / Full Stack with Docker Compose**

`````markdown
**Note**: The first time you start the stack, it might take a minute for all the services to be ready. To monitor it, use `docker compose logs`, or `docker compose logs backend` for the backend service.

`````

**[2] development.md / FastAPI Project - Development / Pre-commits and code linting / Install prek to run automatically**

`````markdown
runs automatically before each commit.

Using `uv`, you could do it with (make sure you are inside `backend` folder):

```bash
❯ uv run prek install -f
prek installed at `../.git/hooks/pre-commit`
```

`````

**[3] backend/README.md / FastAPI Project - Backend / Local Development**

`````markdown
e
$ docker compose up -d db mailcatcher
```

Then, from `./backend/`, install the dependencies, prepare the database, and start the development server:

```console
$ uv sync
$ uv run bash scripts/prestart.sh

`````

**[4] development.md / FastAPI Project - Development / Pre-commits and code linting / Install prek to run automatically**

`````markdown
rt of the dependencies of the project.

After having the `prek` tool installed and available, you need to "install" it in the local repository, so that it runs automatically before each commit.


`````

**[5] deployment-docker-compose.md / FastAPI Project - Docker Compose Deployment / Deploy with GitHub Actions / Install a Self-Hosted Runner**

`````markdown
See GitHub's guides for [adding a self-hosted runner](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners) and [configuring the runner as a service](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application?
`````

### 混合检索 + 父块

完整覆盖：True；上下文：1747 字符；模型答案：未运行或生成失败（见 answers 逐题状态）

**[1] development.md / FastAPI Project - Development / Full Stack with Docker Compose**

`````markdown
**Note**: The first time you start the stack, it might take a minute for all the services to be ready. To monitor it, use `docker compose logs`, or `docker compose logs backend` for the backend service.


`````

**[2] development.md / FastAPI Project - Development / Pre-commits and code linting / Install prek to run automatically**

`````markdown
#### Install prek to run automatically

`prek` is already part of the dependencies of the project.

After having the `prek` tool installed and available, you need to "install" it in the local repository, so that it runs automatically before each commit.

Using `uv`, you could do it with (make sure you are inside `backend` folder):

```bash
❯ uv run prek install -f
prek installed at `../.git/hooks/pre-commit`
```

The `-f` flag forces the installation, in case there was already a `pre-commit` hook previously installed.

Now whenever you try to commit, e.g. with:

```bash
git commit
```

...prek will run and check and format the code you are about to commit, and will ask you to add that code (stage it) with git again before committing.


`````

**[3] backend/README.md / FastAPI Project - Backend / Local Development**

`````markdown
## Local Development

Run the backend locally and connect it to PostgreSQL in Docker Compose.

From the project root, start PostgreSQL and Mailcatcher:

```console
$ docker compose up -d db mailcatcher
```

Then, from `./backend/`, install the dependencies, prepare the database, and start the development server:

```console
$ uv sync
$ uv run bash scripts/prestart.sh
$ uv run fastapi dev
```

The API is available at `http://localhost:8000`, with automatic interactive docs at `http://localhost:8000/docs`.


`````

## Q01：父块回补没有改善覆盖

问题：本地开发后端需要哪些工具？（top_k=1）

参考要点：Docker；uv 用于 Python 包和环境管理

### 纯向量 + 子块

完整覆盖：False；上下文：349 字符；模型答案：未运行或生成失败（见 answers 逐题状态）

**[1] development.md / FastAPI Project - Development / The .env file**

`````markdown
rver with their Compose service names.

Depending on your workflow, you could want to exclude it from Git, for example if your project is public. In that case, you would have to make sure to set up a way for your CI tools to obtain it while building or deploying your project.

`````

### 混合检索 + 子块

完整覆盖：False；上下文：349 字符；模型答案：未运行或生成失败（见 answers 逐题状态）

**[1] development.md / FastAPI Project - Development / The .env file**

`````markdown
rver with their Compose service names.

Depending on your workflow, you could want to exclude it from Git, for example if your project is public. In that case, you would have to make sure to set up a way for your CI tools to obtain it while building or deploying your project.

`````

### 混合检索 + 父块

完整覆盖：False；上下文：690 字符；模型答案：未运行或生成失败（见 answers 逐题状态）

**[1] development.md / FastAPI Project - Development / The .env file**

`````markdown
## The .env file

The `.env` file contains the shared local defaults, generated keys, passwords, and other configuration. Its hostnames use `localhost` for processes running on your machine. Docker Compose overrides hostnames such as the database and SMTP server with their Compose service names.

Depending on your workflow, you could want to exclude it from Git, for example if your project is public. In that case, you would have to make sure to set up a way for your CI tools to obtain it while building or deploying your project.

One way to do it could be to add each environment variable to your CI/CD system.


`````

## Q03：父块回补没有改善覆盖

问题：后端安装依赖、准备数据库和启动服务的顺序是什么？（top_k=1）

参考要点：在 backend 目录依次运行 uv sync、prestart.sh、fastapi dev

### 纯向量 + 子块

完整覆盖：False；上下文：292 字符；模型答案：未运行或生成失败（见 answers 逐题状态）

**[1] development.md / FastAPI Project - Development / Full Stack with Docker Compose**

`````markdown
**Note**: The first time you start the stack, it might take a minute for all the services to be ready. To monitor it, use `docker compose logs`, or `docker compose logs backend` for the backend service.

`````

### 混合检索 + 子块

完整覆盖：False；上下文：292 字符；模型答案：未运行或生成失败（见 answers 逐题状态）

**[1] development.md / FastAPI Project - Development / Full Stack with Docker Compose**

`````markdown
**Note**: The first time you start the stack, it might take a minute for all the services to be ready. To monitor it, use `docker compose logs`, or `docker compose logs backend` for the backend service.

`````

### 混合检索 + 父块

完整覆盖：False；上下文：293 字符；模型答案：未运行或生成失败（见 answers 逐题状态）

**[1] development.md / FastAPI Project - Development / Full Stack with Docker Compose**

`````markdown
**Note**: The first time you start the stack, it might take a minute for all the services to be ready. To monitor it, use `docker compose logs`, or `docker compose logs backend` for the backend service.


`````
