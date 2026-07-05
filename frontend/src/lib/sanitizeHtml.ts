/**
 * Sanitizacao basica de HTML gerado pelo backend.
 * Permite apenas tags e atributos usados no corretor ortografico.
 * Nao substitui DOMPurify para casos complexos, mas reduz superficie XSS.
 */

const ALLOWED_TAGS = new Set([
  "b",
  "strong",
  "i",
  "em",
  "u",
  "span",
  "p",
  "br",
  "div",
  "mark",
  "small",
]);

const ALLOWED_ATTRIBUTES: Record<string, Set<string>> = {
  span: new Set(["style"]),
  div: new Set(["class"]),
  p: new Set(["class"]),
};

const ALLOWED_CSS_PROPS = new Set([
  "background-color",
  "color",
  "font-weight",
  "text-decoration",
]);

function sanitizeStyle(style: string): string {
  const declarations: string[] = [];
  for (const decl of style.split(";")) {
    const colon = decl.indexOf(":");
    if (colon === -1) continue;
    const prop = decl.slice(0, colon).trim().toLowerCase();
    const value = decl.slice(colon + 1).trim();
    if (ALLOWED_CSS_PROPS.has(prop) && /^[\w\s#().,-/%]+$/i.test(value)) {
      declarations.push(`${prop}: ${value}`);
    }
  }
  return declarations.join("; ");
}

export function sanitizeHtml(raw: string): string {
  const parser = new DOMParser();
  const doc = parser.parseFromString(raw, "text/html");

  function walk(node: Node): Node | null {
    if (node.nodeType === Node.TEXT_NODE) {
      return document.createTextNode(node.textContent || "");
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return null;
    }

    const el = node as Element;
    const tag = el.tagName.toLowerCase();
    if (!ALLOWED_TAGS.has(tag)) {
      const fragment = document.createDocumentFragment();
      el.childNodes.forEach((child) => {
        const cleaned = walk(child);
        if (cleaned) fragment.appendChild(cleaned);
      });
      return fragment;
    }

    const clean = document.createElement(tag);
    const allowedAttrs = ALLOWED_ATTRIBUTES[tag];
    if (allowedAttrs) {
      for (const attr of Array.from(el.attributes)) {
        if (!allowedAttrs.has(attr.name)) continue;
        if (attr.name === "style") {
          const safeStyle = sanitizeStyle(attr.value);
          if (safeStyle) clean.setAttribute("style", safeStyle);
        } else {
          clean.setAttribute(attr.name, attr.value);
        }
      }
    }

    el.childNodes.forEach((child) => {
      const cleaned = walk(child);
      if (cleaned) clean.appendChild(cleaned);
    });
    return clean;
  }

  const fragment = document.createDocumentFragment();
  Array.from(doc.body.childNodes).forEach((child) => {
    const cleaned = walk(child);
    if (cleaned) fragment.appendChild(cleaned);
  });

  const tmp = document.createElement("div");
  tmp.appendChild(fragment);
  return tmp.innerHTML;
}
