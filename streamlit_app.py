from pathlib import Path
import time
import streamlit as st
import inngest
from dotenv import load_dotenv
import requests

load_dotenv()

st.set_page_config(page_title="RAG PDF System", page_icon="📄", layout="wide")


@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    return inngest.Inngest(
        app_id="rag_app", 
        is_production=False
    )


def save_uploaded_pdf(file) -> Path:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_bytes = file.getbuffer()
    file_path.write_bytes(file_bytes)
    return file_path


def get_run_output(event_id: str, timeout: int = 120) -> dict:
    """Poll for run output"""
    start_time = time.time()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(
                f"http://127.0.0.1:8288/v1/events/{event_id}/runs"
            )
            
            if response.status_code == 200:
                data = response.json()
                runs = data.get("data", [])
                
                if runs:
                    run = runs[0]
                    status = run.get("status", "")
                    
                    elapsed = time.time() - start_time
                    progress = min(elapsed / timeout, 1.0)
                    progress_bar.progress(progress)
                    status_text.text(f"Status: {status}")
                    
                    if status in ["Completed", "Succeeded", "Finished"]:
                        progress_bar.empty()
                        status_text.empty()
                        return {
                            "success": True,
                            "output": run.get("output", {})
                        }
                    
                    if status in ["Failed", "Cancelled"]:
                        progress_bar.empty()
                        status_text.empty()
                        return {
                            "success": False,
                            "error": f"Run {status}"
                        }
            
            time.sleep(0.5)
        
        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            return {"success": False, "error": str(e)}
    
    progress_bar.empty()
    status_text.empty()
    return {"success": False, "error": "Timeout"}


# Main UI
st.title("📄 RAG PDF System")

# Sidebar
with st.sidebar:
    st.header("🔧 System Status")
    
    try:
        requests.get("http://127.0.0.1:8288/", timeout=1)
        st.success("✅ Inngest")
    except:
        st.error("❌ Inngest")
    
    try:
        requests.get("http://127.0.0.1:8000/api/inngest", timeout=1)
        st.success("✅ FastAPI")
    except:
        st.error("❌ FastAPI")
    
    try:
        requests.get("http://localhost:6333/", timeout=1)
        st.success("✅ Qdrant")
    except:
        st.error("❌ Qdrant")
    
    st.divider()
    st.link_button("📊 Inngest Dashboard", "http://localhost:8288/runs")

# Two columns
col1, col2 = st.columns(2)

# Upload section
with col1:
    st.header("1️⃣ Upload PDF")
    uploaded = st.file_uploader("Choose a PDF", type=["pdf"])
    
    if uploaded:
        if st.button("🚀 Ingest PDF", use_container_width=True):
            with st.spinner("Processing..."):
                try:
                    path = save_uploaded_pdf(uploaded)
                    client = get_inngest_client()
                    
                    # ✅ Use send_sync() - synchronous, no async issues!
                    event_ids = client.send_sync(
                        inngest.Event(
                            name="rag/ingest_pdf",
                            data={
                                "pdf_path": str(path.resolve()),
                                "source_id": path.name
                            }
                        )
                    )
                    
                    if event_ids:
                        st.success("✅ Ingestion triggered!")
                        
                        # Wait for completion
                        result = get_run_output(event_ids[0])
                        
                        if result["success"]:
                            output = result["output"]
                            st.success(f"✅ Ingested {output.get('ingested', 0)} chunks!")
                        else:
                            st.error(f"❌ {result.get('error')}")
                    else:
                        st.warning("Event sent but no ID received")
                        
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

# Query section
with col2:
    st.header("2️⃣ Ask Questions")
    
    with st.form("query_form"):
        question = st.text_input(
            "Your question",
            placeholder="e.g., Who is Chitraksh Suri?"
        )
        top_k = st.slider("Number of chunks", 1, 10, 5)
        submitted = st.form_submit_button("🔍 Search", use_container_width=True)
        
        if submitted and question.strip():
            try:
                client = get_inngest_client()
                
                # ✅ Use send_sync() - synchronous, no async issues!
                event_ids = client.send_sync(
                    inngest.Event(
                        name="rag/query_pdf_ai",
                        data={
                            "question": question.strip(),
                            "top_k": top_k
                        }
                    )
                )
                
                if event_ids:
                    with st.spinner("Generating answer..."):
                        result = get_run_output(event_ids[0])
                        
                        if result["success"]:
                            output = result["output"]
                            
                            st.subheader("💡 Answer")
                            st.write(output.get("answer", "No answer"))
                            
                            sources = output.get("sources", [])
                            if sources:
                                st.subheader("📚 Sources")
                                for source in sources:
                                    st.caption(f"• {source}")
                        else:
                            st.error(f"❌ {result.get('error')}")
                else:
                    st.warning("Query sent but no ID received")
                    
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

st.divider()
st.caption("💡 **Tip:** Results appear directly in this interface!")