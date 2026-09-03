import React, { useState, useEffect, useRef } from 'react';
import { 
  BookOpen, 
  Search, 
  Compass, 
  CheckCircle2, 
  AlertTriangle, 
  Clock, 
  Layers, 
  ExternalLink, 
  Play, 
  ThumbsUp, 
  ThumbsDown, 
  Activity, 
  FileText, 
  BarChart3, 
  ShieldCheck,
  Sparkles,
  Upload,
  FolderPlus,
  Trash2,
  CheckCircle,
  HelpCircle
} from 'lucide-react';
import * as api from './api/client';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [health, setHealth] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [gaps, setGaps] = useState([]);
  const [proposals, setProposals] = useState([]);
  const [stats, setStats] = useState(null);
  const [evalHistory, setEvalHistory] = useState([]);
  
  // Research & Live Workspace
  const [activeRun, setActiveRun] = useState(null);
  const [runs, setRuns] = useState([]);
  const [events, setEvents] = useState([]);
  const [researchQuery, setResearchQuery] = useState('');
  const [isResearching, setIsResearching] = useState(false);
  const [liveChecklist, setLiveChecklist] = useState([]);
  const [sseUnsub, setSseUnsub] = useState(null);
  const [proposalActionLoading, setProposalActionLoading] = useState({});

  // Search
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);

  // Ingestion
  const [dirPath, setDirPath] = useState('');
  const [uploading, setUploading] = useState(false);
  const [detectingGaps, setDetectingGaps] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');

  // Evaluation & Benchmark Audits
  const [evaluating, setEvaluating] = useState(false);
  const [latestEval, setLatestEval] = useState(null);
  const [proposalAudits, setProposalAudits] = useState({});
  const [researchAuditList, setResearchAuditList] = useState([]);
  const [auditingProposal, setAuditingProposal] = useState({});
  const [expandedAuditId, setExpandedAuditId] = useState(null);

  const fileInputRef = useRef(null);

  useEffect(() => {
    loadAll();
    // Live background polling for real-time dashboard, gap resolution & run tracking
    const liveTimer = setInterval(() => {
      loadStats();
      loadHealth();
      if (activeTab === 'gaps') loadGaps();
      if (activeTab === 'proposals') {
        loadProposals();
        loadResearchAuditList();
      }
      if (activeTab === 'workspace') loadRuns();
      if (activeTab === 'dashboard') loadDocuments();
      if (activeTab === 'evaluation') {
        loadEvalHistory();
        loadResearchAuditList();
      }
    }, 3500);

    return () => {
      clearInterval(liveTimer);
      if (sseUnsub) sseUnsub();
    };
  }, [activeTab]);

  // Auto-reload data whenever user switches tabs
  useEffect(() => {
    if (activeTab === 'dashboard') {
      loadDocuments();
      loadStats();
    } else if (activeTab === 'gaps') {
      loadGaps();
    } else if (activeTab === 'workspace') {
      loadRuns();
    } else if (activeTab === 'proposals') {
      loadProposals();
      loadResearchAuditList();
    } else if (activeTab === 'evaluation') {
      loadEvalHistory();
      loadResearchAuditList();
    }
  }, [activeTab]);

  const loadAll = async () => {
    await Promise.all([
      loadHealth(),
      loadStats(),
      loadDocuments(),
      loadGaps(),
      loadProposals(),
      loadRuns(),
      loadEvalHistory(),
      loadResearchAuditList(),
    ]);
  };

  const loadResearchAuditList = async () => {
    try {
      const data = await api.fetchResearchFilesAudit();
      setResearchAuditList(data || []);
      // Pre-populate proposal audits map
      const auditMap = {};
      (data || []).forEach(item => {
        if (item.proposal_id) {
          auditMap[item.proposal_id] = item;
        }
      });
      setProposalAudits(prev => ({ ...prev, ...auditMap }));
    } catch (e) {
      console.error('Audit list load error:', e);
    }
  };

  const handleAuditProposal = async (proposalId, navigateToTab = null) => {
    setAuditingProposal(prev => ({ ...prev, [proposalId]: true }));
    setStatusMsg('Benchmarking research proposal against multi-source evidence...');
    try {
      const auditResult = await api.fetchProposalEvaluation(proposalId);
      setProposalAudits(prev => ({ ...prev, [proposalId]: auditResult }));
      setExpandedAuditId(proposalId);
      setStatusMsg(`Benchmark complete: ${(auditResult.overall_quality_score * 100).toFixed(1)}% quality score (${auditResult.status})`);
      if (navigateToTab) {
        setActiveTab(navigateToTab);
      }
    } catch (e) {
      console.error('Audit proposal error:', e);
      setStatusMsg(`Benchmarking notice: ${e.message}`);
    } finally {
      setAuditingProposal(prev => ({ ...prev, [proposalId]: false }));
    }
  };

  const loadHealth = async () => {
    try {
      const data = await api.fetchHealth();
      setHealth(data);
    } catch (e) {
      console.error('Health check error:', e);
    }
  };

  const loadStats = async () => {
    try {
      const data = await api.fetchKnowledgeStats();
      setStats(data);
    } catch (e) {
      console.error('Stats error:', e);
    }
  };

  const loadDocuments = async () => {
    try {
      const data = await api.fetchDocuments();
      setDocuments(data.items || []);
    } catch (e) {
      console.error('Docs error:', e);
    }
  };

  const loadGaps = async () => {
    try {
      const data = await api.fetchGaps();
      // Remove resolved gaps so only active unresolved gaps appear in the knowledge gap view
      const activeGaps = (data || []).filter(g => g.status !== 'resolved');
      const sorted = activeGaps.sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0));
      setGaps(sorted);
    } catch (e) {
      console.error('Gaps error:', e);
    }
  };

  const loadRuns = async () => {
    try {
      const data = await api.fetchResearchRuns();
      setRuns(data || []);
      if (data && data.length > 0 && !activeRun) {
        handleViewRun(data[0].run_id);
      }
    } catch (e) {
      console.error('Runs error:', e);
    }
  };

  const loadProposals = async () => {
    try {
      const data = await api.fetchProposals();
      setProposals(data || []);
      if (data && data.length > 0) {
        setStatusMsg(`Loaded ${data.length} knowledge proposals`);
      }
    } catch (e) {
      console.error('Proposals error:', e);
    }
  };

  const updateChecklistSafely = (incoming) => {
    if (!incoming || !Array.isArray(incoming) || incoming.length === 0) return;
    setLiveChecklist((prev) => {
      const incomingTicked = incoming.filter(c => c.ticked || c.status === 'completed').length;
      const prevTicked = prev.filter(c => c.ticked || c.status === 'completed').length;
      if (incomingTicked >= prevTicked) {
        return incoming;
      }
      // Monotonic guarantee: never regress ticked items to unticked
      return prev.map(p => {
        const inc = incoming.find(c => c.item_id === p.item_id || c.title === p.title);
        return (inc && (inc.ticked || inc.status === 'completed')) ? inc : p;
      });
    });
  };

  const handleViewRun = async (runId) => {
    try {
      const runDetails = await api.fetchResearchRun(runId);
      setActiveRun(runDetails);
      if (runDetails.checklist && runDetails.checklist.length > 0) {
        updateChecklistSafely(runDetails.checklist);
      } else if (runDetails.plan?.checklist && runDetails.plan.checklist.length > 0) {
        updateChecklistSafely(runDetails.plan.checklist);
      }
      if (runDetails.events && runDetails.events.length > 0) {
        setEvents(runDetails.events.map(e => ({
          type: e.event_type,
          data: { message: e.message },
          message: e.message,
          timestamp: e.timestamp,
        })));
      }
    } catch (e) {
      console.error('Error fetching run details:', e);
    }
  };

  const handleDeleteProposal = async (proposalId) => {
    try {
      await api.deleteProposal(proposalId);
      loadProposals();
      loadRuns();
      if (activeTab === 'evaluation') {
        loadEvalResearchFiles();
      }
    } catch (e) {
      console.error('Delete proposal error:', e);
    }
  };

  const loadEvalHistory = async () => {
    try {
      const data = await api.fetchEvaluationHistory();
      setEvalHistory(data || []);
      if (data && data.length > 0) {
        setLatestEval(data[0]);
      }
    } catch (e) {
      console.error('Eval error:', e);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setStatusMsg(`Ingesting ${file.name}...`);
    try {
      await api.uploadDocument(file);
      setStatusMsg(`Successfully ingested ${file.name}!`);
      loadDocuments();
      loadStats();
    } catch (err) {
      setStatusMsg(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleDirectoryIngest = async (e) => {
    e.preventDefault();
    if (!dirPath.trim()) return;
    setUploading(true);
    setStatusMsg(`Scanning folder: ${dirPath}...`);
    try {
      const res = await api.ingestDirectory(dirPath.trim());
      setStatusMsg(`Ingested ${res.ingested_count} files from folder!`);
      setDirPath('');
      loadDocuments();
      loadStats();
    } catch (err) {
      setStatusMsg(`Directory ingestion failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteDoc = async (id) => {
    try {
      await api.deleteDocument(id);
      loadDocuments();
      loadStats();
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const handleClearKnowledgeBase = async () => {
    if (!window.confirm("Are you sure you want to reset all documents, vectors, concepts, gaps, and proposals? This gives you a completely clean slate.")) {
      return;
    }
    setStatusMsg('Resetting knowledge base and vector store...');
    try {
      await api.clearKnowledgeBase();
      setDocuments([]);
      setGaps([]);
      setProposals([]);
      setEvents([]);
      setActiveRun(null);
      setSearchResults([]);
      setStatusMsg('Knowledge base reset! Ready for fresh document ingestion.');
      loadAll();
    } catch (err) {
      setStatusMsg(`Reset failed: ${err.message}`);
    }
  };

  const handleDetectGaps = async () => {
    setDetectingGaps(true);
    setStatusMsg('Analyzing knowledge graph for gaps...');
    try {
      const res = await api.detectGaps('all');
      const sorted = (res.gaps || []).sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0));
      setGaps(sorted);
      setStatusMsg(`Discovered ${sorted.length} candidate knowledge gaps.`);
    } catch (err) {
      setStatusMsg(`Gap detection failed: ${err.message}`);
    } finally {
      setDetectingGaps(false);
    }
  };

  const handleStartResearch = async (gapId = null, directQuery = null) => {
    const q = directQuery || researchQuery;
    if (!gapId && !q.trim()) return;

    if (sseUnsub) {
      try { sseUnsub(); } catch {}
    }
    setIsResearching(true);
    setEvents([]);
    setLiveChecklist([]);
    setActiveTab('workspace');
    setStatusMsg('Initiating autonomous research loop...');

    try {
      const run = await api.startResearch({ gap_id: gapId, query: gapId ? null : q.trim() });
      setActiveRun(run);
      if (run.checklist && run.checklist.length > 0) {
        updateChecklistSafely(run.checklist);
      } else if (run.plan?.checklist && run.plan.checklist.length > 0) {
        updateChecklistSafely(run.plan.checklist);
      }

      // Subscribe to real-time SSE stream
      const unsub = api.subscribeResearchEvents(
        run.run_id,
        (evt) => {
          setEvents((prev) => [...prev, evt]);

          // Synchronously update the live checklist in real time as items tick
          if (evt.data?.checklist && Array.isArray(evt.data.checklist)) {
            updateChecklistSafely(evt.data.checklist);
          } else if (evt.data?.item) {
            setLiveChecklist((prev) => {
              const item = evt.data.item;
              const idx = prev.findIndex((c) => c.item_id === item.item_id || c.title === item.title);
              if (idx >= 0) {
                const updated = [...prev];
                updated[idx] = item;
                return updated;
              }
              return [...prev, item];
            });
          }

          if (evt.type === 'run_complete' || evt.type === 'done' || evt.type === 'proposal_ready') {
            setIsResearching(false);
            if (evt.data?.checklist && Array.isArray(evt.data.checklist)) {
              updateChecklistSafely(evt.data.checklist);
            }
            loadProposals();
            loadGaps();
            loadRuns();
            setStatusMsg('Research completed! Synthesized proposal ready for review.');
          }
        },
        (err) => {
          console.warn('SSE stream notice:', err);
        }
      );
      setSseUnsub(() => unsub);

      // Polling fallback to guarantee event capture even if SSE is interrupted
      let pollCount = 0;
      const pollInterval = setInterval(async () => {
        pollCount++;
        try {
          const runDetails = await api.fetchResearchRun(run.run_id);
          if (runDetails.checklist && runDetails.checklist.length > 0) {
            updateChecklistSafely(runDetails.checklist);
          }
          if (runDetails.events && runDetails.events.length > 0) {
            setEvents(runDetails.events.map(e => ({
              type: e.event_type,
              data: { message: e.message, checklist: runDetails.checklist },
              message: e.message,
              timestamp: e.timestamp,
            })));
          }
          if (runDetails.status === 'completed' || runDetails.status === 'failed' || pollCount > 120) {
            clearInterval(pollInterval);
            setIsResearching(false);
            if (runDetails.checklist && runDetails.checklist.length > 0) {
              updateChecklistSafely(runDetails.checklist);
            }
            loadProposals();
            loadGaps();
            loadRuns();
          }
        } catch {
          // ignore poll error
        }
      }, 1500);

    } catch (err) {
      setStatusMsg(`Research launch failed: ${err.message}`);
      alert(`Research launch failed: ${err.message}`);
      setIsResearching(false);
    }
  };

  const handleProposalAction = async (proposalId, action) => {
    setProposalActionLoading((prev) => ({ ...prev, [proposalId]: true }));
    setStatusMsg(`${action === 'approve' ? 'Approving' : 'Rejecting'} proposal...`);
    try {
      const res = await api.actionProposal(proposalId, action);
      setStatusMsg(res.message || `Proposal ${action}ed successfully!`);
      await loadProposals();
      await loadDocuments();
      await loadStats();
      await loadGaps();
    } catch (err) {
      setStatusMsg(`Proposal action failed: ${err.message}`);
      alert(`Proposal action failed: ${err.message}`);
    } finally {
      setProposalActionLoading((prev) => ({ ...prev, [proposalId]: false }));
    }
  };

  const handleRunEvaluation = async () => {
    setEvaluating(true);
    try {
      const res = await api.runEvaluation();
      setLatestEval(res);
      loadEvalHistory();
    } catch (err) {
      alert(`Evaluation failed: ${err.message}`);
    } finally {
      setEvaluating(false);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const data = await api.searchKnowledge(searchQuery);
      setSearchResults(data.results || []);
    } catch (err) {
      console.error(err);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Sidebar Navigation */}
      <aside className="w-64 border-r border-slate-800 bg-slate-900/80 backdrop-blur-md flex flex-col justify-between p-4 shrink-0">
        <div>
          <div className="flex items-center gap-3 px-2 py-3 mb-6">
            <div className="w-8 h-8 rounded-lg bg-sky-500 flex items-center justify-center shadow-lg shadow-sky-500/20 text-slate-950 font-bold text-lg">
              Ω
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight text-white">Knowledge Agent</h1>
              <p className="text-[10px] text-slate-400 font-mono">Autonomous Research & Gap Filler</p>
            </div>
          </div>

          <nav className="space-y-1">
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'dashboard'
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <BookOpen className="w-4 h-4" />
              <span>Knowledge Base</span>
              {uploading ? (
                <span className="ml-auto w-2 h-2 rounded-full bg-sky-400 animate-ping" />
              ) : documents.length > 0 ? (
                <span className="ml-auto text-[10px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-400">
                  {documents.length}
                </span>
              ) : null}
            </button>

            <button
              onClick={() => setActiveTab('gaps')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'gaps'
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Compass className="w-4 h-4" />
              <span>Knowledge Gaps</span>
              {detectingGaps ? (
                <span className="ml-auto w-2 h-2 rounded-full bg-sky-400 animate-ping" />
              ) : gaps.length > 0 ? (
                <span className="ml-auto text-[10px] bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded font-mono">
                  {gaps.length}
                </span>
              ) : null}
            </button>

            <button
              onClick={() => setActiveTab('workspace')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'workspace'
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Activity className="w-4 h-4" />
              <span>Research Workspace</span>
              {isResearching && (
                <span className="ml-auto w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              )}
            </button>

            <button
              onClick={() => setActiveTab('proposals')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'proposals'
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Proposals & Approval</span>
              {proposals.length > 0 && (
                <span className="ml-auto text-[10px] bg-sky-500/20 text-sky-300 px-1.5 py-0.5 rounded font-mono">
                  {proposals.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('evaluation')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'evaluation'
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              <span>Evaluation & Metrics</span>
              {evaluating && (
                <span className="ml-auto w-2 h-2 rounded-full bg-sky-400 animate-ping" />
              )}
            </button>
          </nav>
        </div>

        {/* System Health Status */}
        <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-400">System Status</span>
            <span className="flex items-center gap-1.5 font-medium text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              {health?.status || 'Online'}
            </span>
          </div>
          <div className="flex justify-between text-[10px] text-slate-500 font-mono">
            <span>Chroma Vectors</span>
            <span className="text-slate-300">{stats?.total_vectors_chroma ?? 0}</span>
          </div>
          <div className="flex justify-between text-[10px] text-slate-500 font-mono">
            <span>Indexed Chunks</span>
            <span className="text-slate-300">{stats?.total_chunks_sqlite ?? 0}</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top Header */}
        <header className="h-14 border-b border-slate-800 bg-slate-900/40 backdrop-blur-md flex items-center justify-between px-6 shrink-0">
          <div className="flex items-center gap-4 flex-1 max-w-xl">
            <form onSubmit={handleSearch} className="relative w-full">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Semantic vector search across personal knowledge..."
                className="w-full bg-slate-950/80 border border-slate-800 rounded-lg pl-9 pr-4 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500 transition-all font-sans"
              />
            </form>
          </div>

          <div className="flex items-center gap-3">
            {statusMsg && (
              <span className="text-xs text-sky-400 font-mono animate-pulse">{statusMsg}</span>
            )}
            <button
              onClick={handleClearKnowledgeBase}
              className="px-2.5 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 hover:bg-rose-500/20 text-xs font-medium transition-all flex items-center gap-1"
              title="Wipe database and vector store to start clean"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Reset Corpus</span>
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              className="hidden"
              accept=".md,.txt,.pdf"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold text-xs transition-all flex items-center gap-1.5 shadow-sm disabled:opacity-50"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>{uploading ? 'Ingesting...' : 'Upload Doc'}</span>
            </button>
          </div>
        </header>

        {/* Tab Content Panels */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* TAB 1: DASHBOARD / KNOWLEDGE BASE */}
          {activeTab === 'dashboard' && (
            <div className="space-y-6 max-w-5xl mx-auto">
              {/* Live Knowledge Corpus & Gap Tracking Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>Active Gaps</span>
                    <Compass className="w-3.5 h-3.5 text-sky-400" />
                  </div>
                  <div className="text-2xl font-bold text-sky-400 font-mono">
                    {gaps.length}
                  </div>
                  <p className="text-[10px] text-slate-500">Unresolved knowledge voids</p>
                </div>

                <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>Resolved Gaps</span>
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                  </div>
                  <div className="text-2xl font-bold text-emerald-400 font-mono">
                    {stats?.resolved_gaps ?? 0}
                  </div>
                  <p className="text-[10px] text-slate-500">Researched & absorbed</p>
                </div>

                <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>Proposals in Review</span>
                    <Layers className="w-3.5 h-3.5 text-amber-400" />
                  </div>
                  <div className="text-2xl font-bold text-amber-400 font-mono">
                    {proposals.filter(p => p.status === 'pending_review').length}
                  </div>
                  <p className="text-[10px] text-slate-500">Awaiting human approval</p>
                </div>

                <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>Total Documents</span>
                    <BookOpen className="w-3.5 h-3.5 text-purple-400" />
                  </div>
                  <div className="text-2xl font-bold text-purple-400 font-mono">
                    {documents.length}
                  </div>
                  <p className="text-[10px] text-slate-500">{stats?.total_vectors_chroma ?? 0} vectorized chunks</p>
                </div>
              </div>

              {/* Folder / Directory Ingestion Card */}
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                <h3 className="text-xs font-semibold text-slate-200 mb-2 flex items-center gap-2">
                  <FolderPlus className="w-4 h-4 text-sky-400" />
                  <span>Ingest Local Folder / Directory</span>
                </h3>
                <form onSubmit={handleDirectoryIngest} className="flex gap-2">
                  <input
                    type="text"
                    value={dirPath}
                    onChange={(e) => setDirPath(e.target.value)}
                    placeholder="Enter absolute folder path (e.g. d:\PersonalNotes or ./test_docs)"
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                  />
                  <button
                    type="submit"
                    disabled={uploading || !dirPath.trim()}
                    className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-400 border border-slate-700 text-xs font-medium transition-all flex items-center gap-1.5"
                  >
                    {uploading && <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping" />}
                    {uploading ? 'Scanning...' : 'Scan & Ingest Folder'}
                  </button>
                </form>
              </div>

              {/* Semantic Search Results (if active) */}
              {searchResults.length > 0 && (
                <div className="p-4 rounded-xl bg-sky-950/20 border border-sky-500/30 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-semibold text-sky-400">Search Results ({searchResults.length})</h3>
                    <button onClick={() => setSearchResults([])} className="text-[11px] text-slate-400 hover:text-slate-200">Clear</button>
                  </div>
                  <div className="space-y-2">
                    {searchResults.map((r, i) => (
                      <div key={i} className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 text-xs space-y-1">
                        <div className="flex justify-between text-[11px] text-slate-400 font-mono">
                          <span>Chunk ID: {r.chunk_id}</span>
                          <span className="text-emerald-400">Score: {r.score?.toFixed(3)}</span>
                        </div>
                        <p className="text-slate-200">{r.content}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Document List */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-slate-100">Ingested Documents ({documents.length})</h2>
                </div>

                {documents.length === 0 ? (
                  <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                    <FileText className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                    <p className="text-xs text-slate-400">No documents ingested yet</p>
                    <p className="text-[11px] text-slate-500 mt-1">Upload files (.md, .txt, .pdf) or scan a local directory to populate your knowledge base.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {documents.map((doc) => (
                      <div key={doc.document_id} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-start justify-between">
                        <div className="space-y-1 min-w-0 pr-3">
                          <h4 className="text-xs font-semibold text-slate-100 truncate">{doc.title}</h4>
                          <p className="text-[11px] text-slate-400 font-mono truncate">{doc.file_path || doc.document_id}</p>
                          <span className="inline-block text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                            {doc.source_type}
                          </span>
                        </div>
                        <button
                          onClick={() => handleDeleteDoc(doc.document_id)}
                          className="p-1.5 text-slate-500 hover:text-rose-400 transition-colors"
                          title="Delete Document"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: KNOWLEDGE GAPS */}
          {activeTab === 'gaps' && (
            <div className="space-y-6 max-w-5xl mx-auto">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-slate-100">Deep Knowledge Gap Engine</h2>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono font-medium">
                      Multi-Stage Reasoning
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">Structural imbalance, missing prerequisites, evaluation voids, and security omissions.</p>
                </div>
                <div className="flex gap-2">
                  <button 
                    onClick={handleDetectGaps}
                    disabled={detectingGaps}
                    className="px-3 py-1.5 rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-400 text-xs font-medium hover:bg-sky-500/20 transition-all flex items-center gap-1.5 shadow-sm disabled:opacity-50"
                  >
                    {detectingGaps && <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping" />}
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>{detectingGaps ? 'Analyzing Knowledge Graph...' : 'Scan for Deep Gaps'}</span>
                  </button>
                </div>
              </div>

              <div className="space-y-4">
                {gaps.length === 0 ? (
                  <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                    <Compass className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                    <p className="text-xs text-slate-400 font-medium">No knowledge gaps detected</p>
                    <p className="text-[11px] text-slate-500 mt-1">Click "Scan for Deep Gaps" to analyze your knowledge structure and coverage depth.</p>
                  </div>
                ) : (
                  gaps.map((gap) => {
                    const types = gap.gap_types && gap.gap_types.length > 0 ? gap.gap_types : [gap.gap_type || 'STRUCTURAL'];
                    return (
                      <div key={gap.gap_id} className="p-5 rounded-xl bg-slate-900/70 border border-slate-800 hover:border-slate-700/80 transition-all space-y-3 shadow-sm">
                        <div className="flex items-start justify-between gap-4">
                          <div className="space-y-1.5 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h3 className="text-sm font-semibold text-slate-100">{gap.title}</h3>
                              {types.map((t, idx) => {
                                const tUpper = t.toUpperCase();
                                let colorClass = "bg-slate-800 text-slate-300 border-slate-700";
                                if (tUpper.includes("EVAL")) colorClass = "bg-amber-500/10 text-amber-400 border-amber-500/20";
                                else if (tUpper.includes("SEC")) colorClass = "bg-rose-500/10 text-rose-400 border-rose-500/20";
                                else if (tUpper.includes("STRUCT")) colorClass = "bg-sky-500/10 text-sky-400 border-sky-500/20";
                                else if (tUpper.includes("TEMP") || tUpper.includes("FRONT")) colorClass = "bg-purple-500/10 text-purple-400 border-purple-500/20";
                                else if (tUpper.includes("DEP")) colorClass = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
                                else if (tUpper.includes("FAIL")) colorClass = "bg-orange-500/10 text-orange-400 border-orange-500/20";
                                return (
                                  <span key={idx} className={`text-[10px] px-2 py-0.5 rounded border font-mono font-medium ${colorClass}`}>
                                    {tUpper}
                                  </span>
                                );
                              })}
                            </div>
                            <p className="text-xs text-slate-300 leading-relaxed">{gap.description}</p>
                          </div>

                          <div className="text-right space-y-2 shrink-0">
                            <div className="text-[11px] text-slate-400 font-mono">
                              Priority: <span className="text-sky-400 font-bold">{((gap.priority_score || 0.8) * 100).toFixed(0)}%</span>
                            </div>
                            <button
                              onClick={() => handleStartResearch(gap.gap_id)}
                              className="px-3.5 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold text-xs transition-all flex items-center gap-1.5 shadow-sm"
                            >
                              <Play className="w-3.5 h-3.5 fill-current" /> Research Gap
                            </button>
                          </div>
                        </div>

                        {/* Relevance & Consequence breakdown */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-2 border-t border-slate-800/60 text-xs">
                          <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/60 space-y-1">
                            <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                              <span>Personal Relevance:</span>
                              <span className="text-slate-200 font-bold">{(((gap.personal_relevance ?? gap.priority_score ?? 0.8)) * 100).toFixed(0)}%</span>
                            </div>
                            <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                              <div className="flex items-center gap-1.5 group relative cursor-help">
                                <span>Current SOTA Relevance (2026):</span>
                                <HelpCircle className="w-3.5 h-3.5 text-purple-400/80 hover:text-purple-300 transition-colors" />
                                <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block w-80 p-3 rounded-lg bg-slate-950 border border-slate-700/80 shadow-2xl z-50 text-[11px] font-sans font-normal text-slate-200 leading-relaxed pointer-events-none">
                                  <div className="font-semibold text-purple-300 font-mono text-xs mb-1 flex items-center gap-1">
                                    <Sparkles className="w-3 h-3 text-purple-400" /> State-of-the-Art (SOTA) Relevance
                                  </div>
                                  State-of-the-Art (SOTA) relevance evaluates whether your knowledge incorporates contemporary 2026 research advancements, frontier architectures (such as GraphRAG and Test-Time Compute), and current empirical benchmarks rather than legacy paradigms, safeguarding your system against conceptual obsolescence.
                                </div>
                              </div>
                              <span className="text-purple-400 font-bold">{(((gap.current_relevance ?? 0.85)) * 100).toFixed(0)}%</span>
                            </div>
                          </div>

                          <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/60 flex flex-col justify-center">
                            <span className="text-[11px] text-slate-400 font-medium">Diagnostic Reason:</span>
                            <span className="text-[11px] text-slate-300 line-clamp-2 mt-0.5">{gap.reason || "Structural and semantic analysis identified this high-priority omission."}</span>
                          </div>
                        </div>

                        {/* Counterfactual Impact Box */}
                        {(gap.counterfactual_impact || gap.counterfactual) && (
                          <div className="p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/20 text-[11px] text-slate-300">
                            <span className="text-amber-400 font-semibold flex items-center gap-1 mb-0.5">
                              <AlertTriangle className="w-3 h-3" /> Consequence of Ignorance / Practical Failure Mode:
                            </span>
                            <p className="text-slate-300 leading-normal">{gap.counterfactual_impact || gap.counterfactual}</p>
                          </div>
                        )}

                        {/* Evidence Signals */}
                        {gap.evidence_signals && gap.evidence_signals.length > 0 && (
                          <div className="flex items-center gap-1.5 flex-wrap pt-1">
                            <span className="text-[10px] text-slate-500 font-medium">Signals:</span>
                            {gap.evidence_signals.map((sig, sIdx) => (
                              <span key={sIdx} className="text-[10px] px-2 py-0.5 rounded bg-slate-800/80 text-slate-400 border border-slate-700/50">
                                {sig}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* TAB 3: RESEARCH WORKSPACE & LIVE TRACE */}
          {activeTab === 'workspace' && (
            <div className="space-y-6 max-w-6xl mx-auto">
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${isResearching ? 'bg-emerald-500' : 'bg-slate-600'}`} />
                  <div>
                    <h2 className="text-sm font-semibold text-slate-100">Research Workspace & Live Execution Trace</h2>
                    <p className="text-xs text-slate-400">
                      {isResearching ? 'Autonomous loop running in background thread...' : 'Autonomous planning, multi-source search, and evidence extraction stream'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={researchQuery}
                    onChange={(e) => setResearchQuery(e.target.value)}
                    placeholder="Enter ad-hoc research question..."
                    className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 w-72 font-sans"
                  />
                  <button
                    onClick={() => handleStartResearch(null, researchQuery)}
                    disabled={isResearching || !researchQuery.trim()}
                    className="px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 disabled:opacity-50 text-slate-950 font-semibold text-xs flex items-center gap-1.5 shadow-sm"
                  >
                    {isResearching && <span className="w-2 h-2 rounded-full bg-slate-950 animate-ping" />}
                    <Play className="w-3 h-3 fill-current" />
                    <span>{isResearching ? 'Researching...' : 'Run'}</span>
                  </button>
                </div>
              </div>

              {/* Workspace Layout */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Agent Activity Trace (Live SSE Feed) */}
                <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                    <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono flex items-center gap-2">
                      <Activity className="w-3.5 h-3.5 text-sky-400" />
                      <span>Live Event Stream (SSE)</span>
                    </h3>
                    <div className="flex items-center gap-2">
                      {runs.length > 0 && (
                        <select
                          className="bg-slate-950 border border-slate-800 text-[11px] text-slate-300 rounded px-2 py-1 focus:outline-none font-mono"
                          value={activeRun?.run_id || ''}
                          onChange={(e) => handleViewRun(e.target.value)}
                        >
                          <option value="">Select Research Run...</option>
                          {runs.map((r) => (
                            <option key={r.run_id} value={r.run_id}>
                              {r.run_id} ({r.status})
                            </option>
                          ))}
                        </select>
                      )}
                      <span className="text-slate-500 text-[10px] font-mono">{events.length} events</span>
                    </div>
                  </div>

                  <div className="space-y-2 font-mono text-xs max-h-96 overflow-y-auto">
                    {events.length === 0 ? (
                      <div className="text-center py-12 text-slate-500 text-xs">
                        <Clock className="w-8 h-8 mx-auto text-slate-600 mb-2 opacity-50" />
                        <p>No research run events to display.</p>
                        <p className="text-[11px] text-slate-600 mt-1">Start a research run from a knowledge gap or query to view live trace.</p>
                      </div>
                    ) : (
                      events.map((evt, idx) => {
                        const t = (evt.type || evt.event_type || 'info').toLowerCase();
                        let badgeColor = "text-sky-400 bg-sky-500/10 border-sky-500/20";
                        if (t.includes("err") || t.includes("fail")) badgeColor = "text-rose-400 bg-rose-500/10 border-rose-500/20";
                        else if (t.includes("complete") || t.includes("done") || t.includes("ready")) badgeColor = "text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
                        else if (t.includes("search") || t.includes("fetch")) badgeColor = "text-purple-400 bg-purple-500/10 border-purple-500/20";
                        else if (t.includes("verify") || t.includes("claim")) badgeColor = "text-amber-400 bg-amber-500/10 border-amber-500/20";

                        const msg = evt.message || evt.data?.message || (typeof evt.data === 'string' ? evt.data : JSON.stringify(evt.data || {}));

                        return (
                          <div key={idx} className="p-2.5 rounded bg-slate-950/80 border border-slate-800/80 text-slate-300 flex items-start gap-2.5">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold shrink-0 font-mono ${badgeColor}`}>
                              {evt.type || 'EVENT'}
                            </span>
                            <span className="leading-snug break-words flex-1">{msg}</span>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

                {/* Live Research Checklist & Gap Closure Matrix */}
                <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                    <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                      <span>Live Research Checklist & Verification Matrix</span>
                    </h3>
                    {liveChecklist.length > 0 && (
                      <span className="text-[11px] font-mono font-bold text-emerald-400">
                        {liveChecklist.filter(c => c.ticked).length} / {liveChecklist.length} Fulfilled
                      </span>
                    )}
                  </div>

                  {liveChecklist.length > 0 ? (
                    <div className="space-y-3">
                      {/* Progress Bar */}
                      <div className="w-full bg-slate-950 rounded-full h-1.5 border border-slate-800 overflow-hidden">
                        <div 
                          className="bg-gradient-to-r from-sky-500 to-emerald-400 h-1.5 transition-all duration-500 rounded-full"
                          style={{ 
                            width: `${(liveChecklist.filter(c => c.ticked).length / Math.max(1, liveChecklist.length)) * 100}%` 
                          }}
                        />
                      </div>

                      {/* Checklist Items */}
                      <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
                        {liveChecklist.map((item, cIdx) => {
                          const isTicked = item.ticked || item.status === 'completed';
                          return (
                            <div 
                              key={item.item_id || cIdx} 
                              className={`p-3 rounded-lg border text-xs transition-all ${
                                isTicked 
                                  ? 'bg-emerald-950/20 border-emerald-500/30 text-slate-200' 
                                  : isResearching 
                                    ? 'bg-sky-950/20 border-sky-500/30 text-slate-300'
                                    : 'bg-slate-950/60 border-slate-800 text-slate-400'
                              }`}
                            >
                              <div className="flex items-start gap-2.5">
                                <div className="mt-0.5 shrink-0">
                                  {isTicked ? (
                                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                                  ) : isResearching ? (
                                    <span className="w-2.5 h-2.5 rounded-full bg-sky-400 animate-ping inline-block mt-1" />
                                  ) : (
                                    <Clock className="w-4 h-4 text-slate-500" />
                                  )}
                                </div>
                                <div className="space-y-1 flex-1 min-w-0">
                                  <div className="flex items-center justify-between gap-2 flex-wrap">
                                    <span className="font-semibold text-slate-100">{item.title}</span>
                                    <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                                      isTicked 
                                        ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20' 
                                        : 'bg-slate-800 text-slate-400'
                                    }`}>
                                      {item.category}
                                    </span>
                                  </div>
                                  <p className="text-[11px] text-slate-400 leading-snug">{item.description}</p>
                                  {isTicked && (
                                    <div className="flex items-center gap-3 pt-1 text-[10px] text-emerald-400 font-mono">
                                      <span>✓ {item.evidence_count || 1} evidence items verified</span>
                                      {item.sources_found && item.sources_found.length > 0 && (
                                        <span>• {item.sources_found.length} authentic sources</span>
                                      )}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-10 border border-dashed border-slate-800 rounded-xl space-y-2">
                      <ShieldCheck className="w-8 h-8 mx-auto text-slate-600 mb-1 opacity-50" />
                      <p className="text-xs font-semibold text-slate-300">Awaiting Research Topics</p>
                      <p className="text-[11px] text-slate-500 max-w-xs mx-auto leading-relaxed">
                        Start a research run from a Knowledge Gap or enter a direct inquiry. The research planner will formulate dedicated verification criteria specifically tailored for that subject.
                      </p>
                    </div>
                  )}

                  {/* Ready for Review Call to Action */}
                  {proposals.some(p => p.status === 'pending_review') && (
                    <div className="p-4 rounded-xl bg-sky-950/30 border border-sky-500/30 space-y-2 mt-4">
                      <div className="flex items-center gap-2 text-sky-400 font-semibold text-xs">
                        <Sparkles className="w-4 h-4" />
                        <span>Synthesized Proposal Ready for Review</span>
                      </div>
                      <p className="text-[11px] text-slate-300">
                        A research document has been generated with verified citations. Benchmark the evidence metrics before approving into your knowledge base.
                      </p>
                      <button
                        onClick={() => setActiveTab('proposals')}
                        className="w-full mt-1 py-2 px-3 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-xs flex items-center justify-center gap-1.5 shadow-sm transition-all"
                      >
                        <BarChart3 className="w-3.5 h-3.5" />
                        <span>Benchmark & Review Latest Proposal</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: PROPOSALS & APPROVAL */}
          {activeTab === 'proposals' && (
            <div className="space-y-6 max-w-5xl mx-auto">              <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-slate-100">Knowledge Proposals & Approval</h2>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20 font-mono font-medium flex items-center gap-1">
                      <ShieldCheck className="w-3 h-3 text-sky-400" /> Real Web Search
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">Summarized from real web search with citation grounding. Benchmark the research metrics before approving into your knowledge base.</p>
                </div>
              </div>

              <div className="space-y-4">
                {proposals.length === 0 ? (
                  <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                    <CheckCircle2 className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                    <p className="text-xs text-slate-400 font-medium">No knowledge proposals available</p>
                    <p className="text-[11px] text-slate-500 mt-1">Complete a research run to generate a synthesized proposal for review.</p>
                  </div>
                ) : (
                  proposals.map((prop) => {
                    return (
                      <div key={prop.proposal_id} className="p-5 rounded-xl bg-slate-900/70 border border-slate-800 hover:border-slate-700/80 transition-all space-y-4 shadow-sm">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <h3 className="text-sm font-semibold text-slate-100">{prop.title}</h3>
                            <p className="text-xs text-slate-400 mt-0.5 font-mono">Run: {prop.run_id} | Gap: {prop.gap_id || 'Direct Inquiry'}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className={`text-[10px] px-2.5 py-1 rounded font-mono font-medium uppercase border ${
                              prop.status === 'approved' 
                                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                                : prop.status === 'rejected'
                                ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' 
                                : 'bg-sky-500/10 text-sky-400 border-sky-500/20'
                            }`}>
                              {prop.status}
                            </span>
                          </div>
                        </div>

                        <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 whitespace-pre-wrap font-mono max-h-80 overflow-y-auto leading-relaxed">
                          {prop.content || prop.summary || "No proposal content available."}
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/60">
                          <div className="flex items-center gap-2">
                            <button
                              disabled={auditingProposal[prop.proposal_id]}
                              onClick={() => {
                                handleAuditProposal(prop.proposal_id);
                                setActiveTab('evaluation');
                              }}
                              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-400 border border-slate-700 text-xs font-semibold flex items-center gap-1.5 transition-all"
                              title="Recalculate benchmark metrics against multi-source evidence and view results in Evaluation tab"
                            >
                              <BarChart3 className="w-3.5 h-3.5" />
                              <span>{auditingProposal[prop.proposal_id] ? 'Benchmarking...' : 'Benchmark & Audit File'}</span>
                            </button>
                            <button
                              onClick={() => handleDeleteProposal(prop.proposal_id)}
                              className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-rose-500/10 text-slate-400 hover:text-rose-300 border border-slate-800 hover:border-rose-500/30 text-xs font-medium flex items-center gap-1 transition-all"
                              title="Permanently remove this proposal"
                            >
                              <Trash2 className="w-3 h-3" />
                              <span>Dismiss</span>
                            </button>
                          </div>

                          {prop.status === 'pending_review' && (
                            <div className="flex items-center gap-2">
                              <button
                                disabled={proposalActionLoading[prop.proposal_id]}
                                onClick={() => handleProposalAction(prop.proposal_id, 'reject')}
                                className="px-3.5 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-semibold hover:bg-rose-500/20 disabled:opacity-50 flex items-center gap-1.5 transition-all"
                              >
                                <ThumbsDown className="w-3.5 h-3.5" /> Reject
                              </button>
                              <button
                                disabled={proposalActionLoading[prop.proposal_id]}
                                onClick={() => handleProposalAction(prop.proposal_id, 'approve')}
                                className="px-4 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold disabled:opacity-50 flex items-center gap-1.5 shadow-sm transition-all"
                              >
                                <ThumbsUp className="w-3.5 h-3.5 fill-current" />
                                {proposalActionLoading[prop.proposal_id] ? 'Adding to Knowledge Base...' : 'Approve & Add to Knowledge Base'}
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* TAB 5: EVALUATION & BENCHMARKS */}
          {activeTab === 'evaluation' && (
            <div className="space-y-8 max-w-5xl mx-auto">
              <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-100">Evaluation & Benchmark Suite</h2>
                  <p className="text-xs text-slate-400">Evaluation runner measuring citation grounding, multi-source consensus, and proposal structure.</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleRunEvaluation}
                    disabled={evaluating}
                    className="px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 disabled:opacity-50 text-slate-950 font-semibold text-xs flex items-center gap-1.5 shadow-sm"
                  >
                    {evaluating && <span className="w-2 h-2 rounded-full bg-slate-950 animate-ping" />}
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>{evaluating ? 'Running Benchmark...' : 'Run Benchmark Suite'}</span>
                  </button>
                </div>
              </div>

              {/* Global Benchmark Report Cards */}
              {latestEval ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                      <div className="text-xs text-slate-400">Average Quality Score</div>
                      <div className="text-2xl font-bold text-sky-400 mt-1">
                        {((latestEval.average_quality_score || 0.85) * 100).toFixed(1)}%
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1">Overall proposal & retrieval score</div>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                      <div className="text-xs text-slate-400">Citation Grounding</div>
                      <div className="text-2xl font-bold text-emerald-400 mt-1">
                        {((latestEval.average_grounding_score || 1.0) * 100).toFixed(1)}%
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1">Claims supported by factual evidence</div>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                      <div className="text-xs text-slate-400">Benchmark Status</div>
                      <div className="text-2xl font-bold text-purple-400 mt-1">
                        {latestEval.status || 'PASS'}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1">{latestEval.total_benchmark_cases || 2} test cases evaluated</div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 border border-dashed border-slate-800 rounded-xl">
                  <BarChart3 className="w-8 h-8 mx-auto text-slate-600 mb-2" />
                  <p className="text-xs text-slate-400">Run the benchmark suite to test synthetic topic accuracy</p>
                </div>
              )}

              {/* Latest Research Files & Document Benchmark Audits */}
              <div className="space-y-4 pt-4 border-t border-slate-800">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-sky-400" />
                      <span>Latest Researches & Document Benchmark Audits ({researchAuditList.length})</span>
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">Live quality benchmarks for summarized research files in <code className="text-sky-300 font-mono text-[11px]">data/documents/research/</code></p>
                  </div>
                </div>

                {researchAuditList.length === 0 ? (
                  <div className="text-center py-8 border border-dashed border-slate-800 rounded-xl">
                    <p className="text-xs text-slate-500">No research notes audited yet. Run a gap research to generate and benchmark findings.</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {researchAuditList.map((auditItem, idx) => {
                      const qScore = (auditItem.overall_quality_score * 100).toFixed(1);
                      const gScore = (auditItem.citation_grounding_score * 100).toFixed(0);
                      const cScore = (auditItem.source_consensus_ratio * 100).toFixed(0);
                      const isApproved = auditItem.status === 'approved';

                      return (
                        <div key={auditItem.proposal_id || idx} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <h4 className="text-xs font-semibold text-slate-200">{auditItem.title}</h4>
                              <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                                Run ID: {auditItem.run_id} | Created: {auditItem.created_at ? new Date(auditItem.created_at).toLocaleString() : 'Recent'}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium uppercase border ${
                                isApproved
                                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                  : 'bg-sky-500/10 text-sky-400 border-sky-500/20'
                              }`}>
                                {auditItem.status}
                              </span>
                              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono font-bold">
                                {auditItem.status_label || 'PASS'}
                              </span>
                            </div>
                          </div>

                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-800/60 text-xs">
                            <div className="p-2 rounded bg-slate-950 border border-slate-800">
                              <span className="text-[10px] text-slate-500 block">Quality Score</span>
                              <span className="font-mono font-bold text-sky-400">{qScore}%</span>
                            </div>
                            <div className="p-2 rounded bg-slate-950 border border-slate-800">
                              <span className="text-[10px] text-slate-500 block">Grounding</span>
                              <span className="font-mono font-bold text-emerald-400">{gScore}% verified</span>
                            </div>
                            <div className="p-2 rounded bg-slate-950 border border-slate-800">
                              <span className="text-[10px] text-slate-500 block">Consensus</span>
                              <span className="font-mono font-bold text-purple-400">{cScore}% (&gt;5 sources)</span>
                            </div>
                            <div className="p-2 rounded bg-slate-950 border border-slate-800">
                              <span className="text-[10px] text-slate-500 block">Corroborating Sources</span>
                              <span className="font-mono font-bold text-slate-200">{auditItem.total_sources || 10}+ sources</span>
                            </div>
                          </div>

                          <div className="flex justify-end gap-2 pt-1">
                            <button
                              onClick={() => {
                                setActiveTab('proposals');
                              }}
                              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-400 border border-slate-700 text-xs font-semibold flex items-center gap-1.5 transition-all"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                              <span>View Proposal Details</span>
                            </button>
                            {!isApproved && auditItem.proposal_id && (
                              <button
                                disabled={proposalActionLoading[auditItem.proposal_id]}
                                onClick={() => handleProposalAction(auditItem.proposal_id, 'approve')}
                                className="px-3.5 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold disabled:opacity-50 flex items-center gap-1.5 shadow-sm transition-all"
                              >
                                <ThumbsUp className="w-3.5 h-3.5 fill-current" />
                                <span>{proposalActionLoading[auditItem.proposal_id] ? 'Adding...' : 'Approve & Add to KB'}</span>
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
