import logging
import os
import secrets
import uuid
from pathlib import Path
from math import ceil
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import ValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    AccountAlreadyExists,
    SetupUnavailable,
    authenticate_admin,
    create_initial_admin,
    get_active_admin,
    has_active_admin,
    initialize_auth_db,
    register_admin,
    validate_account_fields,
)
from app.implementation import (
    PPEPP_STAGES,
    MonitoringUpdate,
    PpeppStage,
    PpeppStageUpdate,
    delete_stage,
    get_document_implementation,
    implementation_overview,
    save_monitoring,
    save_stage,
    sync_document_registry,
)
from app.user_documents import (
    ALLOWED_EXTENSIONS,
    UPLOADS_DIR,
    DocumentRecord,
    DocumentUpdate,
    all_documents,
    document_file_path,
    drive_download_url,
    drive_preview_url,
    integration_map_documents,
    public_document,
    public_documents,
    public_statistics,
    remove_document,
    save_document,
    safe_local_path,
    standard_tree,
    update_document,
    utc_now,
)
from app.routers.spmi import admin_router as spmi_admin_router

app = FastAPI(
    title="Dashboard Integrasi Dokumen SPMI",
    description="Website visual dashboard untuk dokumen dan foto SPMI",
    version="1.0.0",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(BASE_DIR), "static"))
if not os.path.isdir(STATIC_DIR):
    raise RuntimeError(
        f"Direktori static tidak ditemukan di root proyek: {STATIC_DIR!r}."
    )
TEMPLATE_DIR = os.path.join(os.path.dirname(BASE_DIR), "templates")
logger = logging.getLogger(__name__)
SESSION_SECRET = os.getenv("SPMI_SESSION_SECRET", "").strip()
if len(SESSION_SECRET.encode("utf-8")) < 32:
    SESSION_SECRET = secrets.token_urlsafe(48)
    logger.warning(
        "SPMI_SESSION_SECRET harus memiliki minimal 32 byte; sesi memakai secret sementara dan berakhir saat proses server dimulai ulang."
    )
SETUP_TOKEN = os.getenv("SPMI_ADMIN_SETUP_TOKEN", "").strip()
if SETUP_TOKEN and (len(SETUP_TOKEN) < 32 or not SETUP_TOKEN.isascii()):
    logger.warning("SPMI_ADMIN_SETUP_TOKEN harus berisi minimal 32 karakter ASCII.")

initialize_auth_db()
sync_document_registry(all_documents())

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
MAX_UPLOAD_SIZE = 20 * 1024 * 1024


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def valid_csrf_token(request: Request, supplied_token: str | None) -> bool:
    expected_token = request.session.get("csrf_token")
    return (
        isinstance(expected_token, str)
        and isinstance(supplied_token, str)
        and expected_token.isascii()
        and supplied_token.isascii()
        and secrets.compare_digest(expected_token, supplied_token)
    )


def current_admin(request: Request) -> dict[str, object] | None:
    return get_active_admin(request.session.get("admin_id"))


@app.middleware("http")
async def protect_admin_pages(request: Request, call_next):
    path = request.url.path
    is_admin_page = path == "/admin" or path.startswith("/admin/")
    is_settings_page = path == "/pengaturan"
    public_admin_paths = {"/admin/login", "/admin/register", "/admin/setup"}
    if (is_admin_page and path not in public_admin_paths) or is_settings_page:
        admin = current_admin(request)
        if admin is None:
            return RedirectResponse("/admin/login", status_code=303)
        request.state.admin = admin
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response
    return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="spmi_admin_session",
    max_age=8 * 60 * 60,
    same_site="lax",
    https_only=os.getenv("SPMI_COOKIE_SECURE", "").strip().lower() == "true",
)


def render_page(request: Request, template_name: str, active_page: str, extra_context: dict | None = None):
    context = {
        "request": request,
        "active_page": active_page,
        "admin": getattr(request.state, "admin", None),
        "csrf_token": get_csrf_token(request),
    }
    if extra_context:
        context.update(extra_context)
    return templates.TemplateResponse(request, template_name, context)


@app.get("/admin/login", name="admin_login")
async def admin_login_page(request: Request):
    if current_admin(request):
        return RedirectResponse("/admin/dashboard", status_code=303)
    messages = {
        "registration-success": "Registrasi berhasil. Silakan login dengan akun admin Anda.",
        "logged-out": "Anda telah keluar dari sesi admin.",
    }
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {
            "request": request,
            "csrf_token": get_csrf_token(request),
            "error": "",
            "username_or_email": "",
            "message": messages.get(request.query_params.get("status", ""), ""),
            "setup_available": setup_is_available(),
        },
    )


@app.post("/admin/login")
async def admin_login(request: Request):
    form = await request.form()
    identifier = str(form.get("username_or_email") or "").strip()
    password = str(form.get("password") or "")
    error = ""
    status_code = 400
    account = None
    if not valid_csrf_token(request, str(form.get("csrf_token") or "")):
        error = "Form kedaluwarsa atau tidak valid. Silakan coba kembali."
        status_code = 403
    elif not identifier or not password:
        error = "Username/email dan password wajib diisi."
    else:
        account = authenticate_admin(identifier, password)
        if account is None:
            error = "Username/email atau password salah."

    if account is not None and not error:
        request.session.clear()
        request.session["admin_id"] = account["id"]
        request.session["csrf_token"] = secrets.token_urlsafe(32)
        return RedirectResponse("/admin/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {
            "request": request,
            "csrf_token": get_csrf_token(request),
            "error": error,
            "username_or_email": identifier,
            "message": "",
            "setup_available": setup_is_available(),
        },
        status_code=status_code,
    )


@app.get("/admin/register", name="admin_register")
async def admin_register_page(request: Request):
    if current_admin(request):
        return RedirectResponse("/admin/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin/register.html",
        {"request": request, "csrf_token": get_csrf_token(request), "error": "", "values": {}},
    )


@app.post("/admin/register")
async def admin_register(request: Request):
    form = await request.form()
    values = {
        "full_name": str(form.get("full_name") or "").strip(),
        "username": str(form.get("username") or "").strip(),
        "email": str(form.get("email") or "").strip(),
    }
    password = str(form.get("password") or "")
    confirmation = str(form.get("password_confirmation") or "")
    error = ""
    status_code = 400
    if not valid_csrf_token(request, str(form.get("csrf_token") or "")):
        error = "Form kedaluwarsa atau tidak valid. Silakan muat ulang halaman."
        status_code = 403
    else:
        error = validate_account_fields(
            values["full_name"], values["username"], values["email"], password
        ) or ""
        if not error and password != confirmation:
            error = "Konfirmasi password tidak sama."
        if not error:
            try:
                register_admin(
                    values["full_name"], values["username"], values["email"], password
                )
            except AccountAlreadyExists:
                error = "Username atau email sudah digunakan."
            else:
                return RedirectResponse(
                    "/admin/login?status=registration-success", status_code=303
                )
    return templates.TemplateResponse(
        request,
        "admin/register.html",
        {
            "request": request,
            "csrf_token": get_csrf_token(request),
            "error": error,
            "values": values,
        },
        status_code=status_code,
    )


def setup_is_available() -> bool:
    configured_token = os.getenv("SPMI_ADMIN_SETUP_TOKEN", "").strip()
    return (
        len(configured_token) >= 32
        and configured_token.isascii()
        and not has_active_admin()
    )


@app.get("/admin/setup", name="admin_setup")
async def admin_setup_page(request: Request):
    if not setup_is_available():
        raise HTTPException(status_code=404, detail="Halaman setup tidak tersedia.")
    return templates.TemplateResponse(
        request,
        "admin/setup.html",
        {"request": request, "csrf_token": get_csrf_token(request), "error": "", "values": {}},
    )


@app.post("/admin/setup")
async def admin_setup(request: Request):
    form = await request.form()
    values = {
        "full_name": str(form.get("full_name") or "").strip(),
        "username": str(form.get("username") or "").strip(),
        "email": str(form.get("email") or "").strip(),
    }
    setup_token = str(form.get("setup_token") or "")
    password = str(form.get("password") or "")
    confirmation = str(form.get("password_confirmation") or "")
    configured_token = os.getenv("SPMI_ADMIN_SETUP_TOKEN", "").strip()
    error = ""
    status_code = 400

    if not setup_is_available():
        raise HTTPException(status_code=404, detail="Halaman setup tidak tersedia.")
    if not valid_csrf_token(request, str(form.get("csrf_token") or "")):
        error = "Form kedaluwarsa atau tidak valid. Silakan muat ulang halaman."
        status_code = 403
    elif (
        not configured_token
        or len(setup_token) > 512
        or not setup_token.isascii()
        or not configured_token.isascii()
        or not secrets.compare_digest(setup_token, configured_token)
    ):
        error = "Token setup tidak valid."
        status_code = 403
    else:
        error = validate_account_fields(
            values["full_name"], values["username"], values["email"], password
        ) or ""
        if not error and password != confirmation:
            error = "Konfirmasi password tidak sama."
        if not error:
            try:
                admin_id = create_initial_admin(
                    values["full_name"], values["username"], values["email"], password
                )
            except AccountAlreadyExists:
                error = "Username atau email sudah digunakan."
            except SetupUnavailable:
                raise HTTPException(status_code=404, detail="Setup administrator pertama sudah ditutup.")
            else:
                request.session.clear()
                request.session["admin_id"] = admin_id
                request.session["csrf_token"] = secrets.token_urlsafe(32)
                return RedirectResponse("/admin/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin/setup.html",
        {
            "request": request,
            "csrf_token": get_csrf_token(request),
            "error": error,
            "values": values,
        },
        status_code=status_code,
    )


@app.post("/admin/logout", name="admin_logout")
async def admin_logout(request: Request):
    form = await request.form()
    if not valid_csrf_token(request, str(form.get("csrf_token") or "")):
        raise HTTPException(status_code=403, detail="Form logout tidak valid.")
    request.session.clear()
    return RedirectResponse("/admin/login?status=logged-out", status_code=303)


@app.get("/admin/")
@app.get("/admin/dashboard")
async def dashboard(request: Request):
    return render_page(request, "admin/index.html", "dashboard")


@app.get("/admin/struktur-dokumen")
async def struktur_dokumen(request: Request):
    return render_page(request, "admin/struktur-dokumen.html", "struktur-dokumen")


@app.get("/admin/standar-pt")
async def standar_pt(request: Request):
    return render_page(request, "admin/standar-pt.html", "standar-pt")


@app.get("/admin/pedoman")
async def pedoman(request: Request):
    return render_page(request, "admin/pedoman.html", "pedoman")


@app.get("/admin/sop")
async def sop(request: Request):
    return render_page(request, "admin/sop.html", "sop")


@app.get("/admin/perangkat-spmi", name="perangkat_spmi")
async def perangkat_spmi(request: Request):
    documents = [
        document
        for document in all_documents()
        if str(document.get("tahun_integrasi") or "") == "2025"
        and document.get("source_sheet") == "Integrasi Standar 2025"
    ]
    standards = [
        document
        for document in documents
        if document["kategori"] == "Standar PT"
        and str(document.get("standard_id") or "") == str(document["id"])
    ]
    standard_groups = [
        {
            "standard": standard,
            "documents": [
                document
                for document in documents
                if document["id"] != standard["id"]
                and str(document.get("standard_id") or "") == str(standard["id"])
            ],
        }
        for standard in standards
    ]
    standalone_documents = [
        document for document in documents if not document.get("standard_id")
    ]
    return render_page(
        request,
        "admin/perangkat-spmi.html",
        "perangkat-spmi",
        {
            "integration_year": "2025",
            "integration_sheet": "Integrasi Standar 2025",
            "integration_count": len(documents),
            "standard_groups": standard_groups,
            "standalone_documents": standalone_documents,
        },
    )


@app.get("/admin/peta-integrasi")
async def peta_integrasi(request: Request):
    return render_page(request, "admin/peta-integrasi.html", "peta-integrasi")


@app.get("/admin/monitoring")
async def monitoring(request: Request):
    documents = all_documents()
    return render_page(
        request,
        "admin/monitoring.html",
        "monitoring",
        {"implementations": implementation_overview(documents)},
    )


@app.get("/admin/implementasi")
async def implementasi(request: Request, document_id: str | None = None):
    documents = all_documents()
    sync_document_registry(documents)
    selected = None
    record = None
    if document_id:
        record = get_document_implementation(document_id, documents)
        if record is None:
            raise HTTPException(status_code=404, detail="Dokumen SPMI tidak ditemukan.")
        selected = record["document"]
    stages = record["stages"] if record else {}
    monitoring_data = record["monitoring"] if record else {}
    return render_page(
        request,
        "admin/implementasi.html",
        "implementasi",
        {
            "documents": documents,
            "selected_document": selected,
            "monitoring_data": monitoring_data,
            "ppepp_stages": PPEPP_STAGES,
            "saved_stages": stages,
            "ppepp_count": len(stages),
            "ppepp_complete": len(stages) == len(PPEPP_STAGES)
            and all(
                all(
                    str(stages[stage["key"]].get(field) or "").strip()
                    for field in (
                        "activity",
                        "documents_used",
                        "output",
                        "frequency",
                        "narrative",
                    )
                )
                for stage in PPEPP_STAGES
            ),
        },
    )


@app.get("/admin/laporan")
async def laporan(request: Request):
    return render_page(request, "admin/laporan.html", "laporan")


@app.get("/admin/unduhan")
async def unduhan(request: Request):
    return render_page(request, "admin/unduhan.html", "unduhan")


def _user_context(request: Request, active_page: str, **extra: object):
    return {"request": request, "active_page": active_page, **extra}


def _filtered_documents(
    request: Request,
    kind: str | None = None,
    downloads_only: bool = False,
) -> dict[str, object]:
    documents = public_documents()
    selected_type = kind or request.query_params.get("jenis", "")
    selected_type = {"standar-pt": "Standar PT"}.get(selected_type, selected_type)
    query = request.query_params.get("q", "").strip()
    category = request.query_params.get("kategori", "").strip()
    unit = request.query_params.get("unit", "").strip()
    year = request.query_params.get("tahun", "").strip()
    file_format = request.query_params.get("format", "").strip().upper()
    sort = request.query_params.get("urut", "terbaru")

    allowed_categories = {
        "Kebijakan",
        "Standar PT",
        "Pedoman",
        "SOP",
        "Formulir",
        "Perangkat SPMI",
        "Unduhan",
        "Lainnya",
    }
    if selected_type in allowed_categories:
        documents = [document for document in documents if document["kategori"] == selected_type]
    else:
        selected_type = ""
    if downloads_only:
        documents = [document for document in documents if document["download_allowed"]]
    if query:
        query_lower = query.casefold()
        documents = [
            document
            for document in documents
            if query_lower
            in " ".join(
                str(document[key])
                for key in ("judul", "kategori", "file_url")
            ).casefold()
        ]
    if category:
        documents = [document for document in documents if document["kategori"] == category]
    if year:
        documents = [
            document
            for document in documents
            if document.get("tahun", document["created_at"][:4]) == year
        ]
    if file_format:
        documents = [document for document in documents if document["file_format"] == file_format]

    if sort == "nama":
        documents.sort(key=lambda document: document["judul"].casefold())
    else:
        documents.sort(key=lambda document: document["created_at"], reverse=True)
        sort = "terbaru"

    try:
        page = max(1, int(request.query_params.get("halaman", "1")))
    except ValueError:
        page = 1
    page_size = 12
    total = len(documents)
    page_count = max(1, ceil(total / page_size))
    page = min(page, page_count)
    start = (page - 1) * page_size
    categories = sorted({document["kategori"] for document in public_documents() if document["kategori"]})
    formats = sorted({Path(document["file_url"]).suffix.lstrip(".").upper() for document in public_documents() if document["tipe_sumber"] == "local_file"})
    units = []
    years = sorted(
        {
            document.get("tahun", value[:4])
            for document in public_documents()
            for value in (document["created_at"],)
            if str(document.get("tahun", value[:4])).isdigit()
        },
        reverse=True,
    )
    return {
        "documents": documents[start : start + page_size],
        "total": total,
        "page": page,
        "page_count": page_count,
        "categories": categories,
        "formats": formats,
        "units": units,
        "years": years,
        "filters": {"q": query, "jenis": selected_type, "kategori": category, "unit": unit, "tahun": year, "format": file_format, "urut": sort},
        "document_types": allowed_categories,
    }


@app.get("/", name="user_home")
async def user_home(request: Request):
    documents = public_documents()
    stats = public_statistics()
    counts = {"standar-pt": stats["standar_pt"], "pedoman": stats["pedoman"], "sop": stats["sop"]}
    latest = sorted(documents, key=lambda document: document["created_at"], reverse=True)[:6]
    return templates.TemplateResponse(
        request,
        "beranda.html",
        _user_context(request, "beranda", documents=latest, counts=counts, total=len(documents), categories=sorted({document["kategori"] for document in documents if document["kategori"]})),
    )


@app.get("/katalog", name="user_catalog")
async def user_catalog(request: Request):
    return templates.TemplateResponse(request, "katalog.html", _user_context(request, "katalog", **_filtered_documents(request)))


@app.get("/dokumen/{document_id}", name="user_document_detail")
async def user_document_detail(request: Request, document_id: str):
    document = public_document(document_id)
    if document is None:
        return templates.TemplateResponse(request, "404.html", _user_context(request, "", message="Dokumen tidak ditemukan."), status_code=404)
    related = []
    return templates.TemplateResponse(request, "detail-dokumen.html", _user_context(request, "", document=document, related=related))


@app.get("/standar-pt", name="user_standar_pt")
async def user_standar_pt(request: Request):
    return templates.TemplateResponse(request, "standar-pt.html", _user_context(request, "standar-pt", **_filtered_documents(request, "Standar PT")))


@app.get("/pedoman", name="user_pedoman")
async def user_pedoman(request: Request):
    return templates.TemplateResponse(request, "pedoman.html", _user_context(request, "pedoman", **_filtered_documents(request, "Pedoman")))


@app.get("/kebijakan", name="user_kebijakan")
async def user_kebijakan(request: Request):
    return templates.TemplateResponse(request, "kebijakan.html", _user_context(request, "kebijakan", **_filtered_documents(request, "Kebijakan")))


@app.get("/sop", name="user_sop")
async def user_sop(request: Request):
    return templates.TemplateResponse(request, "sop.html", _user_context(request, "sop", **_filtered_documents(request, "SOP")))


@app.get("/formulir", name="user_formulir")
async def user_formulir(request: Request):
    return templates.TemplateResponse(request, "formulir.html", _user_context(request, "formulir", **_filtered_documents(request, "Formulir")))


@app.get("/peta-integrasi", name="user_integration_map")
async def user_integration_map(request: Request):
    documents = integration_map_documents()
    return templates.TemplateResponse(
        request,
        "peta-integrasi.html",
        _user_context(
            request,
            "peta-integrasi",
            policies=[document for document in documents if document["kategori"] == "Kebijakan"],
            standards=[
                document
                for document in documents
                if document["kategori"] == "Standar PT"
                and str(document.get("standard_id") or "") == str(document["id"])
            ],
            guidelines=[document for document in documents if document["kategori"] == "Pedoman"],
            procedures=[document for document in documents if document["kategori"] == "SOP"],
            forms=[document for document in documents if document["kategori"] == "Formulir"],
            subheadings=[document for document in documents if document["kategori"] == "Lainnya"],
        ),
    )


@app.get("/unduhan", name="user_downloads")
async def user_downloads(request: Request):
    return templates.TemplateResponse(request, "unduhan.html", _user_context(request, "unduhan", **_filtered_documents(request, downloads_only=True)))


@app.get("/tentang", name="user_about")
async def user_about(request: Request):
    return templates.TemplateResponse(request, "tentang.html", _user_context(request, "tentang"))


@app.get("/dokumen/{document_id}/unduh", name="user_document_download")
async def user_document_download(document_id: str):
    document = public_document(document_id)
    file_path = document_file_path(document_id)
    if document is None or not document["is_downloadable"]:
        raise HTTPException(status_code=404, detail="File dokumen publik tidak ditemukan.")
    if document["tipe_sumber"] == "drive_link":
        return RedirectResponse(drive_download_url(document["file_url"]), status_code=307)
    if file_path is None:
        raise HTTPException(status_code=404, detail="File dokumen publik tidak ditemukan.")
    return FileResponse(file_path, filename=file_path.name, media_type="application/octet-stream")


@app.get("/dokumen/{document_id}/preview", name="user_document_preview")
async def user_document_preview(document_id: str):
    document = public_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Pratinjau PDF tidak tersedia.")
    if document["tipe_sumber"] == "drive_link":
        return RedirectResponse(drive_preview_url(document["file_url"]), status_code=307)
    local_path = safe_local_path(document["file_url"])
    if local_path is None or not local_path.is_file():
        raise HTTPException(status_code=404, detail="File dokumen publik tidak ditemukan.")
    if local_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Pratinjau inline hanya tersedia untuk PDF.")
    return FileResponse(local_path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


def require_admin(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, object] | None:
    expected_token = os.getenv("SPMI_ADMIN_TOKEN", "").strip()
    scheme, _, supplied_token = (authorization or "").partition(" ")
    if (
        expected_token
        and expected_token.isascii()
        and supplied_token.isascii()
        and scheme.lower() == "bearer"
        and secrets.compare_digest(supplied_token, expected_token)
    ):
        return None
    admin = current_admin(request)
    if admin is None:
        raise HTTPException(status_code=401, detail="Autentikasi admin diperlukan.")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not valid_csrf_token(
        request, request.headers.get("x-csrf-token")
    ):
        raise HTTPException(status_code=403, detail="Token CSRF tidak valid.")
    return admin


app.include_router(
    spmi_admin_router,
    dependencies=[Depends(require_admin)],
)


@app.get("/api/documents/public")
async def api_public_documents():
    documents = public_documents()
    return {"documents": documents, "statistics": public_statistics()}


@app.get("/api/peta-integrasi/standards/{standard_id}/tree")
async def api_standard_tree(standard_id: str):
    tree = standard_tree(standard_id)
    if tree is None:
        raise HTTPException(status_code=404, detail=f"Standar {standard_id} tidak ditemukan")
    return tree


@app.get("/api/admin/documents")
async def api_admin_documents(_: dict | None = Depends(require_admin)):
    return {"documents": all_documents()}


def _implementation_record(document_id: str) -> dict:
    documents = all_documents()
    record = get_document_implementation(document_id, documents)
    if record is None:
        raise HTTPException(status_code=404, detail="Dokumen SPMI tidak ditemukan.")
    return record


@app.get("/api/admin/implementations")
async def api_admin_implementations(_: dict | None = Depends(require_admin)):
    return {"implementations": implementation_overview(all_documents())}


@app.get("/api/admin/implementations/{document_id}")
async def api_admin_implementation(
    document_id: str,
    _: dict | None = Depends(require_admin),
):
    record = _implementation_record(document_id)
    return {
        "document": record["document"],
        "monitoring": record["monitoring"],
        "stages": record["stages"],
    }


@app.put("/api/admin/implementations/{document_id}/monitoring")
async def api_update_implementation_monitoring(
    document_id: str,
    payload: MonitoringUpdate,
    _: dict | None = Depends(require_admin),
):
    _implementation_record(document_id)
    return {"monitoring": save_monitoring(document_id, payload)}


@app.put("/api/admin/implementations/{document_id}/ppepp/{stage}")
async def api_save_ppepp_stage(
    document_id: str,
    stage: PpeppStage,
    payload: PpeppStageUpdate,
    _: dict | None = Depends(require_admin),
):
    _implementation_record(document_id)
    try:
        saved = save_stage(document_id, stage, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"stage": saved}


@app.delete("/api/admin/implementations/{document_id}/ppepp/{stage}")
async def api_delete_ppepp_stage(
    document_id: str,
    stage: PpeppStage,
    _: dict | None = Depends(require_admin),
):
    _implementation_record(document_id)
    if not delete_stage(document_id, stage):
        raise HTTPException(status_code=404, detail="Data tahap PPEPP tidak ditemukan.")
    return {"deleted": stage, "document_id": document_id}


@app.post("/api/admin/documents", status_code=201)
async def api_create_document(
    judul: str = Form(...),
    kategori: str = Form(...),
    tipe_sumber: str = Form(...),
    status: str = Form("draft"),
    is_downloadable: bool = Form(False),
    file_url: str = Form(""),
    file: UploadFile | None = File(default=None),
    _: None = Depends(require_admin),
):
    document_id = f"doc-{uuid.uuid4().hex[:12]}"
    stored_path: Path | None = None
    if tipe_sumber == "local_file":
        if file is None or not file.filename:
            raise HTTPException(status_code=422, detail="Berkas wajib dipilih")
        extension = Path(file.filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail="Format yang diizinkan hanya PDF atau DOCX")
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        stored_name = f"{document_id}{extension}"
        stored_path = UPLOADS_DIR / stored_name
        size = 0
        signature_checked = False
        try:
            with stored_path.open("wb") as destination:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_SIZE:
                        raise HTTPException(status_code=413, detail="Ukuran maksimal berkas 20 MB")
                    if not signature_checked:
                        valid_signature = chunk.startswith(b"%PDF-") if extension == ".pdf" else chunk.startswith(b"PK\x03\x04")
                        if not valid_signature:
                            raise HTTPException(status_code=415, detail="Isi berkas tidak sesuai dengan ekstensi PDF/DOCX")
                        signature_checked = True
                    destination.write(chunk)
                if not signature_checked:
                    raise HTTPException(status_code=415, detail="Berkas kosong atau format tidak valid")
        except Exception:
            if stored_path.exists():
                stored_path.unlink()
            raise
        finally:
            await file.close()
        file_url = f"/uploads/{stored_name}"
    try:
        record = DocumentRecord(
            id=document_id,
            judul=judul,
            kategori=kategori,
            tipe_sumber=tipe_sumber,
            file_url=file_url,
            status=status,
            is_downloadable=is_downloadable,
            created_at=utc_now(),
        )
        return {"document": save_document(record)}
    except (ValidationError, ValueError) as exc:
        if stored_path is not None and stored_path.exists():
            stored_path.unlink()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/documents/{document_id}")
async def api_update_document(document_id: str, update: DocumentUpdate, _: None = Depends(require_admin)):
    try:
        document = update_document(document_id, update.model_dump(exclude_unset=True))
    except (ValidationError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if document is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    return {"document": document}


@app.delete("/api/admin/documents/{document_id}")
async def api_delete_document(document_id: str, _: None = Depends(require_admin)):
    try:
        document = remove_document(document_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if document is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    return {"deleted": document_id}


@app.post("/admin/documents/add", status_code=201)
async def admin_add_document(payload: dict, _: dict | None = Depends(require_admin)):
    link = payload.get("link_download") or payload.get("drive_link") or payload.get("file_url")
    if not link:
        raise HTTPException(status_code=422, detail="Link dokumen wajib diisi")
    category = payload.get("kategori")
    if category not in {
        "Kebijakan",
        "Pedoman",
        "SOP",
        "Standar PT",
        "Formulir",
        "Perangkat SPMI",
        "Unduhan",
        "Lainnya",
    }:
        raise HTTPException(status_code=422, detail="Kategori dokumen tidak valid")
    source_type = "local_file" if str(link).startswith("/uploads/") else "drive_link"
    created_at = utc_now()
    try:
        record = DocumentRecord(
            id=f"doc-{uuid.uuid4().hex[:12]}",
            judul=payload.get("judul", ""),
            no_dokumen=payload.get("kode") or payload.get("no_dokumen") or "-",
            kode=payload.get("kode") or payload.get("no_dokumen") or "-",
            tahun=str(payload.get("tahun") or created_at[:4]),
            kategori=category,
            tipe_sumber=source_type,
            file_url=link,
            link_download=link,
            status=payload.get("status", "draft"),
            is_downloadable=bool(payload.get("is_downloadable", True)),
            created_at=created_at,
            standard_id=str(payload.get("standard_id") or ""),
            guideline_id=str(payload.get("guideline_id") or ""),
        )
        return {"document": save_document(record)}
    except (ValidationError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/admin/documents/edit/{document_id}")
async def admin_edit_document(
    document_id: str,
    payload: dict,
    _: dict | None = Depends(require_admin),
):
    try:
        document = update_document(document_id, payload)
    except (ValidationError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if document is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    return {"document": document}


@app.post("/admin/documents/toggle-status/{document_id}")
async def admin_toggle_document_status(
    document_id: str,
    _: dict | None = Depends(require_admin),
):
    document = next((item for item in all_documents() if item["id"] == document_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    status = "privat" if document["status"] == "publik" else "publik"
    try:
        updated = update_document(document_id, {"status": status})
    except (ValidationError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"document": updated}


@app.post("/admin/documents/delete/{document_id}")
async def admin_delete_document(
    document_id: str,
    _: dict | None = Depends(require_admin),
):
    try:
        document = remove_document(document_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if document is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    return {"deleted": document_id}


@app.get("/pengaturan")
async def pengaturan(request: Request):
    return render_page(
        request,
        "admin/pengaturan.html",
        "pengaturan",
    )


@app.get("/health")
def health():
    return {
        "status": "success",
        "message": "Dashboard SPMI aktif",
    }
