"use strict";

const form = document.querySelector("#score-form");
const notice = document.querySelector("#save-status");
const encoder = new TextEncoder();
let priorReceiptUrl = null;

function csvCell(value, protect=false) {
  let text = String(value ?? "");
  if (protect && /^[\s]*[=+\-@]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"','""') + '"';
}

function saveFile(name, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const stamp = new Date().toISOString();
  const fields = JSON.parse(form.dataset.fields);
  const rows = [fields.map(field=>csvCell(field)).join(",")];
  const scored = [];
  for (const card of form.querySelectorAll(".score-scene")) {
    const answers = new Map(
      [...card.querySelectorAll("select,textarea")].map(control=>[control.name,control.value])
    );
    const hasScore = [...answers.values()].some(Boolean);
    if (hasScore) scored.push(card.dataset.id);
    answers.set("blind_scene_id",card.dataset.id);
    answers.set("detail_pair_id",card.dataset.detail);
    answers.set("context_pair_id",card.dataset.context);
    answers.set("scored_at_utc",hasScore?stamp:"");
    rows.push(fields.map(field=>csvCell(answers.get(field),field==="failure_reason"||field==="remarks")).join(","));
  }
  notice.hidden = false;
  if (!scored.length) {
    notice.textContent = "请先填写至少一项，或直接下载空白 CSV。";
    return;
  }
  const name = "user_scores_" + stamp.replace(/\W/g,"") + ".csv";
  const body = "\uFEFF" + rows.join("\r\n") + "\r\n";
  const bytes = encoder.encode(body);
  saveFile(name, new Blob([bytes],{type:"text/csv;charset=utf-8"}));
  if (priorReceiptUrl) URL.revokeObjectURL(priorReceiptUrl);
  if (!crypto.subtle) {
    notice.textContent = "评分 CSV 已下载。此浏览器没有本地哈希接口，可按说明用系统命令记录 SHA256。";
    return;
  }
  try {
    const buffer = await crypto.subtle.digest("SHA-256",bytes);
    const sha256 = [...new Uint8Array(buffer)].map(n=>n.toString(16).padStart(2,"0")).join("");
    const receipt = {file:name,created_at_utc:stamp,sha256,scored_scene_ids:scored,origin:"USER_FORM"};
    priorReceiptUrl = URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)+"\n"],{type:"application/json"}));
    const link = document.createElement("a");
    link.download = name.replace(/\.csv$/,".receipt.json");
    link.href = priorReceiptUrl;
    link.textContent = "下载校验凭证";
    notice.textContent = "评分 CSV 已下载。";
    notice.append(link);
  } catch {
    notice.textContent = "评分 CSV 已下载。请按说明用系统命令记录 SHA256。";
  }
});
