FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/ ./
COPY scripts/versioning.mjs scripts/versioning.d.mts /build/scripts/
COPY scripts/install-frontend.mjs /build/scripts/
COPY version.json CHANGELOG.md /build/
# 下载缓存跨源码改动和失败构建保留；仅对明确的网络故障有限重试整次严格安装。
# 可选原生依赖下载失败时 npm 仍可能成功退出；缓存安装层前确认构建器可加载。
RUN --mount=type=cache,id=evolution-npm,target=/root/.npm,sharing=locked \
    node /build/scripts/install-frontend.mjs \
    && node -e "require('node:module').createRequire(require.resolve('@umijs/bundler-utoopack'))('@utoo/pack')"
ARG COMMIT_SHA
ARG RELEASE_TAG
ARG SOURCE_DIRTY
ARG PREVIEW_VERSION
RUN node /build/scripts/versioning.mjs build-info --output /build/build-info.json
ENV BUILD_INFO_FILE=/build/build-info.json
RUN npm run build

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv/backend:/srv
WORKDIR /srv/backend
COPY backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/requirements-build.lock ./
# 构建工具独立锁定并缓存下载，不随业务源码变化重新解析隔离构建依赖。
RUN --mount=type=cache,id=evolution-pip-build,target=/root/.cache/pip,sharing=locked \
    python -m pip install --disable-pip-version-check --only-binary=:all: --require-hashes -r requirements-build.lock
COPY backend/ ./
COPY --from=frontend /build/build-info.json /srv/backend/app/_build_info.json
# 本地打包必须离线完成；校验已安装的构建依赖，不再创建在线构建隔离环境。
RUN --network=none python -m pip install --disable-pip-version-check --no-cache-dir --no-deps --no-build-isolation --check-build-dependencies --no-index .
COPY --from=frontend /build/frontend/dist /srv/frontend/dist
COPY deploy/ /srv/deploy/
RUN useradd --create-home --uid 10001 organization
USER organization
EXPOSE 8000
CMD ["python", "-m", "deploy.supervise"]
