const form = document.querySelector('#planner-form');
const resultEl = document.querySelector('#result');
const historyEl = document.querySelector('#history');
const statusEl = document.querySelector('#form-status');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  statusEl.textContent = 'Agent 正在调用交通、住宿、目的地和预算工具…';
  const values = new FormData(form);
  const payload = {
    origin: values.get('origin'), destination: values.get('destination'), days: Number(values.get('days')),
    budget_cny: values.get('budget_cny') ? Number(values.get('budget_cny')) : null,
    travelers: Number(values.get('travelers')), pace: values.get('pace'), lodging_preference: values.get('lodging_preference'),
    interests: values.get('interests').split(/[，,]/).map(value => value.trim()).filter(Boolean),
  };
  try {
    const response = await fetch('/api/travel-plans', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    if (!response.ok) throw new Error('生成失败，请检查输入。');
    renderPlan(await response.json());
    statusEl.textContent = '计划已生成并保存，可展开各模块查看细节。';
  } catch (error) { statusEl.textContent = error.message; }
});

document.querySelector('#history-button').addEventListener('click', async () => {
  const records = await (await fetch('/api/travel-plans?limit=8')).json();
  historyEl.classList.remove('hidden');
  historyEl.innerHTML = `<h2>历史计划</h2><div class="history-list"></div>`;
  const list = historyEl.querySelector('.history-list');
  records.forEach(record => {
    const button = document.querySelector('#history-item-template').content.firstElementChild.cloneNode(true);
    button.innerHTML = `<strong>${escapeHtml(record.request.origin)} → ${escapeHtml(record.request.destination)}</strong><small>${record.request.days} 日 · ¥${record.result.total_cost_cny ?? '待补全'} / 人</small>`;
    button.addEventListener('click', () => renderPlan(record)); list.append(button);
  });
});

function renderPlan(record) {
  const {request: rawRequest, result} = record; const request = {...rawRequest, origin: escapeHtml(rawRequest.origin), destination: escapeHtml(rawRequest.destination), pace: escapeHtml(rawRequest.pace), lodging_preference: escapeHtml(rawRequest.lodging_preference)}; const d = result.details || {}; const budget = d.budget || {};
  resultEl.classList.remove('hidden');
  resultEl.innerHTML = `
    <div class="result-header"><div><p class="eyebrow">${record.id.slice(0, 8).toUpperCase()} · 已保存</p><h2>${request.destination} ${request.days} 日完整决策包</h2><p>${request.travelers} 人出行 · ${request.pace} 节奏 · ${request.lodging_preference}住宿</p></div><span class="pill">${result.complete ? '计划完整' : '需要补充资料'}</span></div>
    <div class="metric-grid"><div class="metric"><span>人均预算</span><strong>¥${budget.per_person_cny ?? '—'}</strong></div><div class="metric"><span>${request.travelers} 人合计</span><strong>¥${budget.group_total_cny ?? '—'}</strong></div><div class="metric"><span>往返交通</span><strong>¥${budget.transport_cny ?? '—'}</strong></div></div>
    <div class="module-grid">${card('行 · 交通', transportHtml(d.transport))}${card('住 · 住宿', stayHtml(d.stay))}${card('吃喝 · 餐厅与饮品', listHtml([...(d.food || []), ...(d.drinks || [])], item => `${item.name} · ${item.cuisine || item.kind} · ¥${item.avg_cost_cny}`))}${card('本地出行', listHtml(d.local_transport || [], item => `${item.mode} · ${item.tip} · 日均 ¥${item.avg_cost_cny}`))}</div>
    <h3>逐日行程</h3><div class="timeline">${(d.itinerary || []).map(day => `<details><summary>第 ${day.day} 天 · ¥${day.estimated_cost_cny} <span class="pill">${day.pace}</span></summary><div class="detail-body"><p>上午：${day.morning.name}（${day.morning.area}，门票 ¥${day.morning.ticket_cny}）</p><p>下午：${day.afternoon.name}（${day.afternoon.area}，门票 ¥${day.afternoon.ticket_cny}）</p><p>吃：${day.restaurant.name} · ${day.restaurant.cuisine}（约 ¥${day.restaurant.avg_cost_cny}）</p><p>喝：${day.drink.name} · ${day.drink.kind}（约 ¥${day.drink.avg_cost_cny}）</p><p>行：${day.local_transport.mode} · ${day.local_transport.tip}</p></div></details>`).join('')}</div>
    <h3>预订清单</h3><div class="checklist">${(d.booking_checklist || []).map(item => `<label><input type="checkbox">${item}</label>`).join('')}</div>
    <details><summary>查看 Agent 执行轨迹与提醒</summary><div class="detail-body"><p>${(result.trace || []).join('<br>')}</p><p>${(result.warnings || []).join('<br>')}</p></div></details>`;
  resultEl.scrollIntoView({behavior:'smooth', block:'start'});
}
function card(label, content) { return `<article class="module"><p class="tag">${label}</p>${content}</article>`; }
function transportHtml(value) { return value ? `<h3>${value.recommended.mode}</h3><p>单程约 ${value.recommended.duration_hours} 小时 · ¥${value.recommended.cost_cny}</p><details><summary>查看全部交通选择</summary><div class="detail-body">${listHtml(value.options, item => `${item.mode} · ${item.duration_hours} 小时 · ¥${item.cost_cny}`)}</div></details>` : '<p>暂无交通信息</p>'; }
function stayHtml(value) { return value ? `<h3>${value.name}</h3><p>${value.area} · ${value.style} · ¥${value.avg_cost_cny}/人/晚</p><p>${value.note || ''}</p>` : '<p>暂无住宿信息</p>'; }
function listHtml(items, formatter) { return items.length ? `<p>${items.map(item => `• ${formatter(item)}`).join('<br>')}</p>` : '<p>暂无推荐</p>'; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[character])); }
