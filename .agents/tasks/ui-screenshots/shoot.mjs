import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import { fileURLToPath } from "url";
import path from "path";

const dir = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE || "http://localhost:5173";
const sizes = { d: { width: 1440, height: 900 }, t: { width: 768, height: 1024 } };
const browser = await chromium.launch();
const axeReport = [];

async function open(size, theme, { tour = false, setup } = {}) {
  const ctx = await browser.newContext({ viewport: sizes[size] });
  await ctx.addInitScript(
    ([t, tr]) => {
      localStorage.setItem("acip.theme", t);
      if (!tr) localStorage.setItem("acip.tour.done", "1");
    },
    [theme, tour],
  );
  const page = await ctx.newPage();
  if (setup) await setup(page);
  await page.goto(BASE);
  await page.waitForTimeout(tour ? 1200 : 500);
  return { ctx, page };
}
async function run(page, label) {
  await page.getByRole("button", { name: `Run ${label}` }).click();
}
async function shot(page, name) {
  await page.screenshot({ path: path.join(dir, `${name}.png`), fullPage: true });
}
async function axe(page, name) {
  const r = await new AxeBuilder({ page }).analyze();
  const bad = r.violations.filter((v) => ["serious", "critical"].includes(v.impact));
  axeReport.push({
    name,
    total: r.violations.length,
    bad: bad.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ") + " :: " + (n.any[0]?.message || "")) })),
  });
}
const settle = (p) => p.waitForTimeout(6000);

for (const size of ["d", "t"]) {
  for (const theme of ["light", "dark"]) {
    const s = `${size}-${theme}`;
    let { ctx, page } = await open(size, theme);
    await shot(page, `01-empty-${s}`);
    await axe(page, `01-${s}`);
    await run(page, "Clean shopper");
    await settle(page);
    await shot(page, `04-approve-${s}`);
    await axe(page, `04-${s}`);
    await run(page, "Fraud ring member");
    await settle(page);
    await shot(page, `06-fraud-veto-${s}`);
    await axe(page, `06-${s}`);
    await page.getByRole("button", { name: /Help/ }).first().click();
    await page.waitForTimeout(600);
    await shot(page, `10-help-${s}`);
    await axe(page, `10-${s}`);
    await ctx.close();
  }
  // light-only states
  let o = await open(size, "light", { tour: true });
  await shot(o.page, `02-tour-${size}`);
  await o.ctx.close();

  o = await open(size, "light", {
    setup: (p) =>
      p.route("**/v1/checkout", async (r) => {
        await new Promise((x) => setTimeout(x, 2500));
        await r.continue();
      }),
  });
  await run(o.page, "Clean shopper");
  await o.page.waitForTimeout(800);
  await shot(o.page, `03-evaluating-${size}`);
  await o.ctx.close();

  for (const [n, label] of [
    ["05-challenge", "High-value mid-risk"],
    ["07-policy-veto", "Sanctioned geography"],
    ["11-reroute", "Unhealthy preferred route"],
  ]) {
    o = await open(size, "light");
    await run(o.page, label);
    await settle(o.page);
    await shot(o.page, `${n}-${size}`);
    await o.ctx.close();
  }

  o = await open(size, "light", {
    setup: (p) =>
      p.route("**/v1/transactions/*", (r) => {
        const u = r.request().url();
        if (u.includes("/explain")) return r.continue();
        return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ transaction_id: "x", verdicts: [] }) });
      }),
  });
  await run(o.page, "Clean shopper");
  await o.page.waitForTimeout(9000);
  await shot(o.page, `08-partial-${size}`);
  await o.ctx.close();

  o = await open(size, "light", {
    setup: (p) => p.route("**/localhost:8080/**", (r) => r.abort()),
  });
  await o.page.waitForTimeout(1500);
  await shot(o.page, `09-unreachable-${size}`);
  await o.ctx.close();
}

// focus ring
{
  const { ctx, page } = await open("d", "light");
  for (let i = 0; i < 6; i++) await page.keyboard.press("Tab");
  await page.screenshot({ path: path.join(dir, "12-focus.png") });
  await ctx.close();
}
await browser.close();
console.log(JSON.stringify(axeReport, null, 1));
