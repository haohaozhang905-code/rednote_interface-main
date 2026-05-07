# API 文档工具包

本目录负责小红书接口层的接口定义与 API 预览工具链。

## 目录结构

```text
api-docs/
├── package.json
├── scripts/
│   └── build-openapi-i18n.mjs
├── openapi/
│   ├── openapi.base.yaml      # 唯一接口结构源
│   ├── i18n/
│   │   ├── zh.yaml            # 中文文案源
│   │   └── en.yaml            # 英文文案源
│   ├── dist/
│   │   ├── openapi.zh.yaml    # 生成产物，不要直接编辑
│   │   └── openapi.en.yaml    # 生成产物，不要直接编辑
│   ├── examples/
│   ├── intro.zh.md            # 中文预览首页说明
│   └── intro.en.md            # 英文预览首页说明
└── site/
    ├── index.html             # 双语 Redoc 预览入口
    └── redocly.yaml
```

## 本地预览

```powershell
npm install
npm run build:i18n
npm run preview
```

打开：

```text
http://127.0.0.1:8088/site/
```

默认展示中文界面。右上角可以切换英文，也可以直接访问：

```text
http://127.0.0.1:8088/site/?lang=en
```

## 维护规则

不要直接编辑生成产物：

```text
openapi/dist/openapi.zh.yaml
openapi/dist/openapi.en.yaml
```

正确流程：

1. 在 `openapi/openapi.base.yaml` 中修改接口结构。
2. 在 `openapi/i18n/zh.yaml` 和 `openapi/i18n/en.yaml` 中补齐文案。
3. 执行 `npm run build:i18n`。
4. 执行 `npm run lint`。

常用命令：

```powershell
npm run build:i18n
npm run check:i18n
npm run lint:zh
npm run lint:en
npm run lint
npm run preview
```

`check:i18n` 会在以下情况失败：

- 生成产物过期。
- 翻译文件缺少必要 key。
- 中英文 OpenAPI 除可翻译字段外，与 `openapi/openapi.base.yaml` 发生结构漂移。
