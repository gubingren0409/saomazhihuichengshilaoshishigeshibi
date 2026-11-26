"use strict";
const form=document.querySelector("#scores");
const esc=x=>'"'+String(x).replaceAll('"','""')+'"';
form.addEventListener("submit",event=>{
  event.preventDefault();
  const names=JSON.parse(form.dataset.fields);
  const rows=[names.map(esc).join(",")];
  const t=new Date().toISOString();
  for(const box of form.querySelectorAll("fieldset")){
    const values=Object.fromEntries([...box.querySelectorAll("[name]")].map(x=>[x.name,x.value]));
    values.scored_at_utc=t;
    rows.push(names.map(n=>esc(values[n]||"")).join(","));
  }
  const url=URL.createObjectURL(new Blob(["\uFEFF"+rows.join("\r\n")+"\r\n"],{type:"text/csv;charset=utf-8"}));
  const a=document.createElement("a");
  a.href=url;a.download="user_scores_R3_"+t.replace(/[-:.]/g,"")+".csv";a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  document.querySelector("#save-note").textContent="已生成你的本地评分文件。请保留并在准备好后交给审核。";
});
