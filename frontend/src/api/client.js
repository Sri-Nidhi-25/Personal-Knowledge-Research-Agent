/**
 * API client module for REST endpoints and Server-Sent Events (SSE).
 * Connects the React UI to the Personal Knowledge Research Agent backend.
 */

const API_BASE = '/api/v1';

// --- System & Health ---
export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed with status ${res.status}`);
  return res.json();
}

// --- Documents & Ingestion ---
export async function fetchDocuments(status = null, limit = 50, offset = 0) {
  const params = new URLSearchParams({ limit, offset });
  if (status) params.append('status', status);
  const res = await fetch(`${API_BASE}/documents?${params.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch documents: ${res.statusText}`);
  return res.json();
}

export async function uploadDocument(file, title = '') {
  const formData = new FormData();
  formData.append('file', file);
  if (title) formData.append('title', title);
  const res = await fetch(`${API_BASE}/documents`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  return res.json();
}

export async function ingestDirectory(directoryPath) {
  const res = await fetch(`${API_BASE}/documents/directory`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ directory_path: directoryPath }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Directory ingestion failed: ${res.statusText}`);
  }
  return res.json();
}

export async function deleteDocument(documentId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete document: ${res.statusText}`);
  return res.json();
}

// --- Knowledge Search & Graph ---
export async function searchKnowledge(query, top_k = 5) {
  const res = await fetch(`${API_BASE}/knowledge/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k }),
  });
  if (!res.ok) throw new Error(`Search failed: ${res.statusText}`);
  return res.json();
}

export async function fetchKnowledgeStats() {
  const res = await fetch(`${API_BASE}/knowledge/stats`);
  if (!res.ok) throw new Error(`Failed to fetch stats: ${res.statusText}`);
  return res.json();
}

export async function clearKnowledgeBase() {
  const res = await fetch(`${API_BASE}/knowledge/clear`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to reset knowledge base: ${res.statusText}`);
  return res.json();
}

export async function fetchKnowledgeGraph() {
  const res = await fetch(`${API_BASE}/graph`);
  if (!res.ok) throw new Error(`Failed to fetch graph: ${res.statusText}`);
  return res.json();
}

export async function fetchConcepts() {
  const res = await fetch(`${API_BASE}/concepts`);
  if (!res.ok) throw new Error(`Failed to fetch concepts: ${res.statusText}`);
  return res.json();
}

// --- Knowledge Gaps ---
export async function fetchGaps(status = null) {
  const url = status ? `${API_BASE}/gaps?status=${status}` : `${API_BASE}/gaps`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to list gaps: ${res.statusText}`);
  return res.json();
}

export async function detectGaps(scope = 'all') {
  const res = await fetch(`${API_BASE}/gaps/detect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scope }),
  });
  if (!res.ok) throw new Error(`Gap detection failed: ${res.statusText}`);
  return res.json();
}

export async function createManualGap(title, description, reason = '', priority_score = 0.8) {
  const res = await fetch(`${API_BASE}/gaps`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, description, reason, priority_score }),
  });
  if (!res.ok) throw new Error(`Failed to create gap: ${res.statusText}`);
  return res.json();
}

// --- Research Agent ---
export async function startResearch({ gap_id = null, query = null }) {
  const res = await fetch(`${API_BASE}/research/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gap_id, query }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to start research: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchResearchRuns() {
  const res = await fetch(`${API_BASE}/research/runs`);
  if (!res.ok) throw new Error(`Failed to fetch runs: ${res.statusText}`);
  return res.json();
}

export async function fetchResearchRun(runId) {
  const res = await fetch(`${API_BASE}/research/runs/${runId}`);
  if (!res.ok) throw new Error(`Failed to fetch run: ${res.statusText}`);
  return res.json();
}

export function subscribeResearchEvents(runId, onEvent, onError) {
  const eventSource = new EventSource(`${API_BASE}/research/runs/${runId}/stream`);

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onEvent({ type: event.type || 'message', data });
    } catch {
      onEvent({ type: event.type || 'message', raw: event.data });
    }
  };

  const eventTypes = [
    'run_started', 'searching', 'search_complete', 'fetching',
    'fetch_failed', 'evidence_extracted', 'extraction_complete',
    'claims_synthesized', 'verifying', 'contradictions_found',
    'synthesizing', 'proposal_ready', 'run_complete', 'done', 'error'
  ];

  eventTypes.forEach((evtName) => {
    eventSource.addEventListener(evtName, (event) => {
      try {
        const data = JSON.parse(event.data);
        onEvent({ type: evtName, data });
      } catch {
        onEvent({ type: evtName, raw: event.data });
      }
    });
  });

  eventSource.onerror = (err) => {
    if (onError) onError(err);
    eventSource.close();
  };

  return () => eventSource.close();
}

// --- Proposals & Approval ---
export async function fetchProposals(status = null) {
  const url = status ? `${API_BASE}/research/proposals?status=${status}` : `${API_BASE}/research/proposals`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch proposals: ${res.statusText}`);
  return res.json();
}

export async function fetchProposal(proposalId) {
  const res = await fetch(`${API_BASE}/research/proposals/${proposalId}`);
  if (!res.ok) throw new Error(`Failed to fetch proposal: ${res.statusText}`);
  return res.json();
}

export async function actionProposal(proposalId, action = 'approve', feedback = '') {
  const res = await fetch(`${API_BASE}/research/proposals/${proposalId}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, feedback }),
  });
  if (!res.ok) throw new Error(`Proposal action failed: ${res.statusText}`);
  return res.json();
}

// --- Evaluation & Benchmarks ---
export async function runEvaluation() {
  const res = await fetch(`${API_BASE}/eval/run`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Evaluation benchmark failed: ${res.statusText}`);
  return res.json();
}

export async function fetchEvaluationHistory() {
  const res = await fetch(`${API_BASE}/eval/results`);
  if (!res.ok) throw new Error(`Failed to fetch evaluation history: ${res.statusText}`);
  return res.json();
}
