import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), "..");
const requireFromApiDocs = createRequire(path.join(ROOT, "package.json"));
const YAML = requireFromApiDocs("yaml");
const API_DIR = path.join(ROOT, "openapi");
const BASE_PATH = path.join(API_DIR, "openapi.base.yaml");
const I18N_DIR = path.join(API_DIR, "i18n");
const OUTPUTS = {
  zh: path.join(API_DIR, "dist", "openapi.zh.yaml"),
  en: path.join(API_DIR, "dist", "openapi.en.yaml"),
};

class I18nError extends Error {}

function loadYaml(filePath) {
  return YAML.parse(fs.readFileSync(filePath, "utf8"));
}

function dumpYaml(filePath, data) {
  fs.writeFileSync(
    filePath,
    YAML.stringify(data, { lineWidth: 1000 }),
    "utf8",
  );
}

function deepClone(value) {
  return structuredClone(value);
}

function requirePath(data, dotted) {
  let value = data;
  for (const part of dotted.split(".")) {
    if (!value || typeof value !== "object" || !(part in value)) {
      throw new I18nError(`missing translation key: ${dotted}`);
    }
    value = value[part];
  }
  return value;
}

function operationTranslation(translations, operationId) {
  const operations = requirePath(translations, "operations");
  if (!operations || typeof operations !== "object" || !(operationId in operations)) {
    throw new I18nError(`missing operation translation: ${operationId}`);
  }
  const item = operations[operationId];
  if (!item || typeof item !== "object") {
    throw new I18nError(`operation translation must be an object: ${operationId}`);
  }
  for (const key of ["summary", "description"]) {
    if (!(key in item)) {
      throw new I18nError(`missing operation translation: ${operationId}.${key}`);
    }
  }
  return item;
}

function localize(base, translations) {
  const doc = deepClone(base);
  doc.info.title = requirePath(translations, "info.title");
  doc.info.description = requirePath(translations, "info.description");
  doc.info.license = doc.info.license || {};
  doc.info.license.name = requirePath(translations, "info.license_name");

  if (Array.isArray(doc.servers) && doc.servers.length > 0) {
    doc.servers[0].description = requirePath(translations, "servers.local");
  }

  const tagTranslations = requirePath(translations, "tags");
  for (const tag of doc.tags || []) {
    const name = String(tag.name || "");
    if (!tagTranslations[name]) {
      throw new I18nError(`missing tag translation: ${name}`);
    }
    tag.description = tagTranslations[name].description;
  }

  for (const pathItem of Object.values(doc.paths || {})) {
    if (!pathItem || typeof pathItem !== "object") continue;
    for (const operation of Object.values(pathItem)) {
      if (!operation || typeof operation !== "object" || !operation.operationId) continue;
      const operationId = String(operation.operationId);
      const translated = operationTranslation(translations, operationId);
      operation.summary = translated.summary;
      operation.description = translated.description;
      const responseTexts = translated.responses || {};
      for (const [status, response] of Object.entries(operation.responses || {})) {
        if (response && typeof response === "object" && !("$ref" in response) && status in responseTexts) {
          response.description = responseTexts[status];
        }
      }
    }
  }

  const fields = requirePath(translations, "fields");
  const schemas = doc.components?.schemas || {};
  schemas.CookieLoginActionRequest.properties.cookie.description = fields.cookie;
  schemas.PhoneStartLoginActionRequest.properties.phone.description = fields.phone;
  schemas.PhoneSubmitLoginActionRequest.properties.code.description = fields.code;
  schemas.FetchRootCommentsRequest.properties.note_id.description = fields.note_context_guard;
  schemas.SessionBound.properties.token.description = fields.token_ownership;

  const metaFields = requirePath(translations, "meta");
  schemas.ResponseMeta.description = metaFields.description;
  for (const [field, description] of Object.entries(metaFields.properties || {})) {
    if (schemas.ResponseMeta.properties?.[field]) {
      schemas.ResponseMeta.properties[field].description = description;
    }
  }

  const errorFields = requirePath(translations, "error");
  schemas.ApiError.description = errorFields.description;
  for (const [field, description] of Object.entries(errorFields.properties || {})) {
    if (schemas.ApiError.properties?.[field]) {
      schemas.ApiError.properties[field].description = description;
    }
  }

  const componentResponses = requirePath(translations, "component_responses");
  for (const [name, response] of Object.entries(doc.components?.responses || {})) {
    if (!componentResponses[name]) {
      throw new I18nError(`missing component response translation: ${name}`);
    }
    response.description = componentResponses[name];
  }

  const security = requirePath(translations, "security");
  const schemes = doc.components?.securitySchemes || {};
  if (schemes.AdminApiKey) {
    schemes.AdminApiKey.description = security.admin_api_key;
  }

  return doc;
}

function structuralCopy(value, ancestors = []) {
  const translatableKeys = new Set(["title", "description", "summary"]);
  if (Array.isArray(value)) {
    return value.map((item) => structuralCopy(item, ancestors));
  }
  if (value && typeof value === "object") {
    const result = {};
    for (const [key, item] of Object.entries(value)) {
      if (translatableKeys.has(key)) {
        result[key] = "<i18n>";
      } else if (ancestors.at(-1) === "license" && key === "name") {
        result[key] = "<i18n>";
      } else {
        result[key] = structuralCopy(item, [...ancestors, key]);
      }
    }
    return result;
  }
  return value;
}

function verifyOutputsMatch(base, outputs) {
  const expected = JSON.stringify(structuralCopy(base));
  for (const [locale, doc] of Object.entries(outputs)) {
    const actual = JSON.stringify(structuralCopy(doc));
    if (actual !== expected) {
      throw new I18nError(`generated OpenAPI structure drifted for locale ${locale}`);
    }
  }
}

function relativeToRoot(filePath) {
  return path.relative(ROOT, filePath).replaceAll("\\", "/");
}

function build({ check }) {
  const base = loadYaml(BASE_PATH);
  const generated = {};
  for (const [locale] of Object.entries(OUTPUTS)) {
    const translations = loadYaml(path.join(I18N_DIR, `${locale}.yaml`));
    generated[locale] = localize(base, translations);
  }

  verifyOutputsMatch(base, generated);

  if (check) {
    const stale = [];
    for (const [locale, outputPath] of Object.entries(OUTPUTS)) {
      const current = fs.existsSync(outputPath) ? loadYaml(outputPath) : null;
      if (JSON.stringify(current) !== JSON.stringify(generated[locale])) {
        stale.push(relativeToRoot(outputPath));
      }
    }
    if (stale.length > 0) {
      throw new I18nError(`generated files are stale: ${stale.join(", ")}`);
    }
    return;
  }

  for (const [locale, outputPath] of Object.entries(OUTPUTS)) {
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    dumpYaml(outputPath, generated[locale]);
  }
}

try {
  build({ check: process.argv.includes("--check") });
} catch (error) {
  if (error instanceof I18nError) {
    console.error(`openapi i18n error: ${error.message}`);
    process.exit(1);
  }
  throw error;
}
