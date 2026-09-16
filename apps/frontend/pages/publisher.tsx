import Head from "next/head";
import Link from "next/link";
import type { GetServerSideProps } from "next";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { hasValidSession } from "../lib/session";

type Candidate = {
  page_id: string;
  page_name: string;
  instagram_account_id?: string | null;
  tasks?: string[];
};

type Bound = {
  account_id: string;
  label?: string;
  approved_by?: string;
  bound_at?: string;
};

type Asset = {
  uri: string;
  sha256: string;
  provenance: string;
  media_type: string;
};

async function jsonFetch(url: string, init?: RequestInit) {
  const response = await fetch(url, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error || `Request failed (${response.status})`);
  return data;
}

export default function Publisher() {
  const [status, setStatus] = useState<any>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const [approvedBy, setApprovedBy] = useState("");
  const [selectedPage, setSelectedPage] = useState("");
  const [confirmBind, setConfirmBind] = useState(false);

  const [platform, setPlatform] = useState("facebook");
  const [accountId, setAccountId] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const [caption, setCaption] = useState("");
  const [destination, setDestination] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [queueApprovedBy, setQueueApprovedBy] = useState("");
  const [confirmQueue, setConfirmQueue] = useState(false);

  const [receiptKey, setReceiptKey] = useState("");
  const [receipt, setReceipt] = useState<any>(null);

  const bound: Bound[] = status?.accounts?.bound_accounts?.[platform] || [];

  useEffect(() => {
    if (bound.length && !bound.some((item) => item.account_id === accountId)) setAccountId(bound[0].account_id);
    if (!bound.length) setAccountId("");
  }, [platform, status]);

  const readyToQueue = useMemo(
    () => Boolean(
      campaignId.trim() &&
      accountId &&
      caption.trim() &&
      destination.trim() &&
      queueApprovedBy.trim() &&
      confirmQueue
    ),
    [campaignId, accountId, caption, destination, queueApprovedBy, confirmQueue],
  );

  async function refresh() {
    setError("");
    try {
      const [publisherStatus, candidateStatus] = await Promise.all([
        jsonFetch("/api/publisher/status"),
        jsonFetch("/api/publisher/meta/candidates"),
      ]);
      setStatus(publisherStatus);
      setCandidates(candidateStatus.candidates || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function beginMeta() {
    setBusy("meta");
    setError("");
    try {
      const data = await jsonFetch("/api/publisher/meta/start", { method: "POST" });
      if (!data.authorization_url) throw new Error("Authorization URL missing");
      window.location.assign(data.authorization_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Meta authorization failed");
      setBusy("");
    }
  }

  async function bind() {
    if (!confirmBind) return;
    setBusy("bind");
    setError("");
    setNotice("");
    try {
      await jsonFetch("/api/publisher/meta/bind", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          page_id: selectedPage,
          approved_by: approvedBy,
          human_approval: "APPROVED",
        }),
      });
      setNotice("Account binding recorded with explicit human approval.");
      setConfirmBind(false);
      setSelectedPage("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Binding failed");
    } finally {
      setBusy("");
    }
  }

  function addAsset() {
    setAssets([
      ...assets,
      { uri: "", sha256: "", provenance: "operator", media_type: "application/octet-stream" },
    ]);
  }

  async function queue(event: FormEvent) {
    event.preventDefault();
    if (!confirmQueue) return;
    setBusy("queue");
    setError("");
    setNotice("");
    setReceipt(null);
    try {
      const data = await jsonFetch("/api/publisher/jobs/queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          campaign_id: campaignId,
          platform,
          account_id: accountId,
          caption,
          destination_url: destination,
          scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
          assets,
          approved_by: queueApprovedBy,
          human_approval: "APPROVED",
        }),
      });
      setNotice(`Queued with status ${data.status}. No live publish was attempted.`);
      setConfirmQueue(false);
      setReceiptKey(data.idempotency_key || "");
      if (data.idempotency_key) {
        setReceipt(await jsonFetch(`/api/publisher/receipts/${encodeURIComponent(data.idempotency_key)}`));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Queue failed");
    } finally {
      setBusy("");
    }
  }

  async function lookup(event: FormEvent) {
    event.preventDefault();
    setBusy("receipt");
    setError("");
    try {
      setReceipt(await jsonFetch(`/api/publisher/receipts/${encodeURIComponent(receiptKey.trim())}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Receipt lookup failed");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <Head>
        <title>Dominion Publisher — Control</title>
        <meta name="robots" content="noindex,nofollow" />
      </Head>
      <div className="appShell">
        <header className="topbar">
          <div className="brand">
            <span className="brandMark small">D</span>
            <div>
              <strong>Dominion Publisher</strong>
              <span>Governed operator surface</span>
            </div>
          </div>
          <Link className="button ghost" href="/">Overview</Link>
        </header>

        <main className="content">
          <section className="pageTitle">
            <div>
              <p className="overline">PUBLISHER</p>
              <h1>Connect, approve, queue, prove.</h1>
              <p>Every consequential action is explicit. Credentials stay server-side and live Meta publishing remains held closed.</p>
            </div>
            <button className="button secondary" onClick={refresh} disabled={!!busy}>Refresh status</button>
          </section>

          {error && <div className="alert danger">{error}</div>}
          {notice && <div className="alert success">{notice}</div>}

          <section className="metricGrid compact">
            <article className="metric"><span>Service</span><strong>{status?.health?.status === "ok" ? "ONLINE" : "—"}</strong></article>
            <article className="metric"><span>Meta app</span><strong>{status?.health?.meta_app_configured ? "READY" : "NOT READY"}</strong></article>
            <article className="metric"><span>Facebook</span><strong>{status?.health?.meta_bound_counts?.facebook ?? "—"}</strong></article>
            <article className="metric"><span>Instagram</span><strong>{status?.health?.meta_bound_counts?.instagram ?? "—"}</strong></article>
          </section>

          <section className="panel">
            <div className="sectionHead">
              <div><p className="overline">1 · IDENTITY</p><h2>Meta account authorization</h2></div>
              <span className="status hold">LIVE PUBLISH HOLD</span>
            </div>
            <p className="muted">OAuth authorization creates candidates only. Binding still requires explicit operator approval below.</p>
            <button className="button secondary" onClick={beginMeta} disabled={busy === "meta" || !status?.health?.meta_app_configured}>
              {busy === "meta" ? "Opening Meta…" : "Authorize Meta account"}
            </button>

            {candidates.length > 0 && (
              <div className="approvalBox">
                <h3>Pending binding candidates</h3>
                <div className="candidateList">
                  {candidates.map((candidate) => (
                    <label className={`candidate ${selectedPage === candidate.page_id ? "selected" : ""}`} key={candidate.page_id}>
                      <input type="radio" name="candidate" checked={selectedPage === candidate.page_id} onChange={() => setSelectedPage(candidate.page_id)} />
                      <div>
                        <strong>{candidate.page_name}</strong>
                        <span>Facebook {candidate.page_id}{candidate.instagram_account_id ? ` · Instagram ${candidate.instagram_account_id}` : ""}</span>
                      </div>
                    </label>
                  ))}
                </div>
                <div className="formGrid">
                  <label><span>Approved by</span><input value={approvedBy} onChange={(event) => setApprovedBy(event.target.value)} placeholder="Operator name" /></label>
                </div>
                <label className="check">
                  <input type="checkbox" checked={confirmBind} onChange={(event) => setConfirmBind(event.target.checked)} />
                  <span>I explicitly approve binding this selected Page to Dominion Publisher.</span>
                </label>
                <button className="button primary" onClick={bind} disabled={!selectedPage || !approvedBy.trim() || !confirmBind || busy === "bind"}>
                  {busy === "bind" ? "Binding…" : "Bind approved account"}
                </button>
              </div>
            )}
          </section>

          <section className="panel">
            <div className="sectionHead">
              <div><p className="overline">2 · JOB</p><h2>Queue governed content</h2></div>
              <span className="status ok">QUEUE ONLY</span>
            </div>
            <form className="stack" onSubmit={queue}>
              <div className="formGrid two">
                <label>
                  <span>Platform</span>
                  <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
                    <option value="facebook">Facebook</option>
                    <option value="instagram">Instagram</option>
                  </select>
                </label>
                <label>
                  <span>Bound account</span>
                  <select value={accountId} onChange={(event) => setAccountId(event.target.value)} disabled={!bound.length}>
                    <option value="">{bound.length ? "Select account" : "No bound account"}</option>
                    {bound.map((item) => <option key={item.account_id} value={item.account_id}>{item.label || item.account_id}</option>)}
                  </select>
                </label>
              </div>

              <div className="formGrid two">
                <label><span>Campaign ID</span><input value={campaignId} onChange={(event) => setCampaignId(event.target.value)} placeholder="campaign-2026-09" required /></label>
                <label><span>Schedule (optional)</span><input type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} /></label>
              </div>

              <label><span>Caption</span><textarea rows={6} value={caption} onChange={(event) => setCaption(event.target.value)} placeholder="Final approved content" required /></label>
              <label><span>Destination URL</span><input type="url" value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="https://…" required /></label>

              <div className="sectionHead minor">
                <div><h3>Assets</h3><p className="muted">Optional. Each asset requires immutable SHA-256 provenance.</p></div>
                <button type="button" className="button ghost" onClick={addAsset}>Add asset</button>
              </div>

              {assets.map((asset, index) => (
                <div className="asset" key={index}>
                  <div className="formGrid two">
                    <label><span>Asset URI</span><input value={asset.uri} onChange={(event) => setAssets(assets.map((item, i) => i === index ? { ...item, uri: event.target.value } : item))} /></label>
                    <label><span>Media type</span><input value={asset.media_type} onChange={(event) => setAssets(assets.map((item, i) => i === index ? { ...item, media_type: event.target.value } : item))} /></label>
                  </div>
                  <label><span>SHA-256</span><input value={asset.sha256} maxLength={64} onChange={(event) => setAssets(assets.map((item, i) => i === index ? { ...item, sha256: event.target.value } : item))} /></label>
                  <div className="assetFoot">
                    <label><span>Provenance</span><input value={asset.provenance} onChange={(event) => setAssets(assets.map((item, i) => i === index ? { ...item, provenance: event.target.value } : item))} /></label>
                    <button type="button" className="textButton dangerText" onClick={() => setAssets(assets.filter((_, i) => i !== index))}>Remove</button>
                  </div>
                </div>
              ))}

              <div className="approvalBox">
                <h3>Queue approval</h3>
                <p className="muted">The Publisher requires explicit approval metadata before a job may enter the queue.</p>
                <div className="formGrid">
                  <label><span>Approved by</span><input value={queueApprovedBy} onChange={(event) => setQueueApprovedBy(event.target.value)} placeholder="Operator name" /></label>
                </div>
                <label className="check">
                  <input type="checkbox" checked={confirmQueue} onChange={(event) => setConfirmQueue(event.target.checked)} />
                  <span>I approve this exact content job for queueing. This does not approve live publishing.</span>
                </label>
              </div>

              <div className="holdAction">
                <div><strong>Live publish is disabled by governance.</strong><span>Queueing produces an auditable receipt without creating a public post.</span></div>
                <button className="button primary" disabled={!readyToQueue || busy === "queue"}>{busy === "queue" ? "Queueing…" : "Queue and verify receipt"}</button>
              </div>
            </form>
          </section>

          <section className="panel">
            <div><p className="overline">3 · PROOF</p><h2>Receipt verification</h2></div>
            <form className="receiptLookup" onSubmit={lookup}>
              <input value={receiptKey} onChange={(event) => setReceiptKey(event.target.value)} placeholder="Idempotency key" />
              <button className="button secondary" disabled={!receiptKey.trim() || busy === "receipt"}>{busy === "receipt" ? "Checking…" : "Verify"}</button>
            </form>
            {receipt && <pre className="receipt">{JSON.stringify(receipt, null, 2)}</pre>}
          </section>
        </main>
      </div>
    </>
  );
}

export const getServerSideProps: GetServerSideProps = async ({ req }) =>
  hasValidSession(req) ? { props: {} } : { redirect: { destination: "/login", permanent: false } };
