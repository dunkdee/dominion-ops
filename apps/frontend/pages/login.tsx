import Head from "next/head";
import { FormEvent, useState } from "react";
import { useRouter } from "next/router";
export default function Login() {
  const router = useRouter(); const [key,setKey]=useState(""); const [error,setError]=useState(""); const [busy,setBusy]=useState(false);
  async function submit(event:FormEvent){event.preventDefault();setBusy(true);setError("");try{const response=await fetch("/api/session/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({accessKey:key})});if(!response.ok)throw new Error(response.status===401?"Access key rejected.":"Login service is unavailable.");await router.replace("/");}catch(e){setError(e instanceof Error?e.message:"Login failed.");}finally{setBusy(false);}}
  return <><Head><title>Dominion Control — Sign in</title><meta name="robots" content="noindex,nofollow" /></Head><main className="loginShell"><section className="loginPanel"><div className="brandMark">D</div><h1>Dominion Control</h1><p className="muted">Private operator surface. Credentials remain server-side.</p><form onSubmit={submit} className="stack"><label className="fieldLabel" htmlFor="access">Operator access key</label><input id="access" type="password" autoComplete="current-password" value={key} onChange={e=>setKey(e.target.value)} required />{error&&<div className="alert danger">{error}</div>}<button className="button primary" disabled={busy||!key}>{busy?"Authenticating…":"Enter control plane"}</button></form></section></main></>;
}
