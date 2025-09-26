# app.py
import streamlit as st
import pandas as pd
import io
import os
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import openpyxl

st.set_page_config(page_title="Pagos Escuela de Fútbol", layout="wide")

# ===============================
# 0️⃣ CONFIG - MESES Y CATEGORÍAS
# ===============================
meses = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]
categorias = [str(y) for y in range(2011, 2022)]  # 2011..2021

# ===============================
# 1️⃣  CONFIG: Credenciales & Drive API
# ===============================
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
]

# st.secrets["gcp"] debe contener el JSON del service account
creds_info = st.secrets["gcp"]
creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)

@st.cache_resource
def get_drive_service():
    return build("drive", "v3", credentials=creds)

drive_service = get_drive_service()

# Nombre del archivo en Drive
DRIVE_FILENAME = "Pagos.xlsx"

# ubicación temporal en servidor
TMP_FILEPATH = "/tmp/pagos_drive.xlsx"

# ===============================
# 2️⃣ UTIL: Operaciones con Drive y Excel
# ===============================
def find_file_id_by_name(name):
    """Busca en Drive por nombre (en Mi unidad) y devuelve fileId o None."""
    query = f"name = '{name}' and trashed = false"
    res = drive_service.files().list(q=query, spaces='drive', fields="files(id, name, mimeType)").execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None

def download_file_to_tmp(file_id, dest_path=TMP_FILEPATH):
    """Descarga un archivo de Drive a ruta temporal."""
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.FileIO(dest_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.close()
    return dest_path

def upload_file_replace(file_id, local_path, mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'):
    """Reemplaza un archivo existente en Drive con el contenido local."""
    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
    updated = drive_service.files().update(fileId=file_id, media_body=media).execute()
    return updated

def create_file_from_local(local_path, name=DRIVE_FILENAME, mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'):
    """Crea un nuevo archivo en Drive a partir de un archivo local."""
    file_metadata = {"name": name}
    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
    newf = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return newf

def load_excel_from_drive():
    """Asegura que exista el archivo y lo carga en un dict de DataFrames (sheet_name -> df)."""
    file_id = find_file_id_by_name(DRIVE_FILENAME)
    if file_id:
        # descargar
        download_file_to_tmp(file_id)
        try:
            xls = pd.read_excel(TMP_FILEPATH, sheet_name=None, engine="openpyxl")
        except Exception:
            # archivo vacío o corrupto -> crear estructura vacía
            xls = {}
    else:
        # no existe: crear estructura vacía en memoria
        xls = {}
    # aseguramos todas las hojas necesarias existan (aunque vacías)
    if "Jugadores" not in xls:
        xls["Jugadores"] = pd.DataFrame(columns=["Nombres", "Apellidos", "Documento", "Fecha nacimiento", "Categoría",
                                                 "Nombre acudiente", "Dirección", "Cédula acudiente", "Correo", "Contacto"])
    for c in categorias:
        if c not in xls:
            xls[c] = pd.DataFrame(columns=["Jugador"] + meses)
    if "Uniformes" not in xls:
        xls["Uniformes"] = pd.DataFrame(columns=["Jugador", "Categoría", "Fecha", "Valor", "Observaciones"])
    if "Torneos" not in xls:
        xls["Torneos"] = pd.DataFrame(columns=["Jugador", "Categoría", "Nombre Torneo", "Fecha", "Valor", "Observaciones"])
    return xls, file_id

def save_excel_and_upload(xls_dict, file_id=None):
    """Guarda dict de DataFrames a Excel local y sube a Drive (crea o reemplaza)."""
    # grabar localmente
    with pd.ExcelWriter(TMP_FILEPATH, engine="openpyxl") as writer:
        for sheet_name, df in xls_dict.items():
            # convertir NaN a cadena vacía para que el Excel no muestre NaN
            df_to_write = df.copy()
            df_to_write.fillna("", inplace=True)
            df_to_write.to_excel(writer, sheet_name=sheet_name, index=False)
    # subir
    if file_id:
        upload_file_replace(file_id, TMP_FILEPATH)
    else:
        newf = create_file_from_local(TMP_FILEPATH, name=DRIVE_FILENAME)
        file_id = newf.get("id")
    # opcional: eliminar tmp
    try:
        os.remove(TMP_FILEPATH)
    except Exception:
        pass
    return file_id

# ===============================
# 3️⃣  FUNCIONES PRINCIPALES (lectura y escritura local+drive)
# ===============================
@st.cache_data(ttl=60)
def load_all_from_drive_cached():
    # cachea la lectura por 60s para evitar múltiples descargas seguidas
    xls, fid = load_excel_from_drive()
    return xls, fid

def refresh_sheet_in_memory(xls, sheet_name):
    # reload the sheet from drive (used sparingly)
    xls_new, fid = load_excel_from_drive()
    return xls_new, fid

# ===============================
# 4️⃣  OPERACIONES: Jugadores y pagos (trabajando sobre xls dict)
# ===============================
def add_player_to_xls(xls, player_data):
    df_j = xls["Jugadores"]
    # duplicado por Documento
    if player_data.get("Documento") and (player_data["Documento"].astype(str) if isinstance(player_data["Documento"], pd.Series) else str(player_data["Documento"])) in df_j["Documento"].astype(str).values:
        return False, "Ya existe un jugador con ese documento."
    # append
    df_j = pd.concat([df_j, pd.DataFrame([player_data])], ignore_index=True)
    xls["Jugadores"] = df_j
    # agregar a categoría matriz
    categoria = player_data.get("Categoría")
    nombre_completo = f"{player_data.get('Nombres','').strip()} {player_data.get('Apellidos','').strip()}".strip()
    if categoria in categorias:
        df_cat = xls.get(categoria, pd.DataFrame(columns=["Jugador"] + meses))
        # si ya existe nombre en la categoría, no duplicar
        if nombre_completo not in df_cat["Jugador"].astype(str).values:
            new_row = {"Jugador": nombre_completo}
            for m in meses:
                new_row[m] = 0
            df_cat = pd.concat([df_cat, pd.DataFrame([new_row])], ignore_index=True)
            xls[categoria] = df_cat
    return True, "Jugador agregado en archivo local."

def update_monthly_in_xls(xls, categoria, jugador_nombre, mes, monto):
    df_cat = xls.get(categoria)
    if df_cat is None or df_cat.empty:
        return False, "Hoja de categoría vacía."
    mask = df_cat["Jugador"].astype(str) == str(jugador_nombre)
    if not mask.any():
        return False, "Jugador no encontrado en categoría."
    df_cat.loc[mask, mes] = monto
    xls[categoria] = df_cat
    return True, "Pago actualizado en archivo local."

def append_uniform_in_xls(xls, jugador, categoria, fecha, valor, obs):
    df_uni = xls.get("Uniformes", pd.DataFrame(columns=["Jugador", "Categoría", "Fecha", "Valor", "Observaciones"]))
    row = {"Jugador": jugador, "Categoría": categoria, "Fecha": fecha, "Valor": valor, "Observaciones": obs}
    df_uni = pd.concat([df_uni, pd.DataFrame([row])], ignore_index=True)
    xls["Uniformes"] = df_uni
    return True, "Uniforme agregado en archivo local."

def append_torneo_in_xls(xls, jugador, categoria, nombre_torneo, fecha, valor, obs):
    df_t = xls.get("Torneos", pd.DataFrame(columns=["Jugador", "Categoría", "Nombre Torneo", "Fecha", "Valor", "Observaciones"]))
    row = {"Jugador": jugador, "Categoría": categoria, "Nombre Torneo": nombre_torneo, "Fecha": fecha, "Valor": valor, "Observaciones": obs}
    df_t = pd.concat([df_t, pd.DataFrame([row])], ignore_index=True)
    xls["Torneos"] = df_t
    return True, "Torneo agregado en archivo local."

# ===============================
# 5️⃣ INTERFAZ STREAMLIT (UI) - usa xls en memoria y sube cuando haya cambios
# ===============================
st.title("⚽ Sistema de pagos - Escuela de Fútbol (Drive Excel)")

# Cargar inicialmente (cacheada)
xls, file_id = load_all_from_drive_cached()

menu = st.sidebar.radio("📂 Navegación", ["👥 Gestión de jugadores", "💸 Registrar pago", "📊 Ver datos", "🔁 Sincronizar"])

# ---------- GESTIÓN DE JUGADORES ----------
if menu == "👥 Gestión de jugadores":
    st.header("👥 Gestión de jugadores")
    with st.expander("Agregar nuevo jugador"):
        with st.form("form_add_player"):
            Nombres = st.text_input("Nombres")
            Apellidos = st.text_input("Apellidos")
            Documento = st.text_input("Documento")
            Fecha_nac = st.date_input("Fecha de nacimiento")
            Categoria = st.selectbox("Categoría", categorias)
            Nombre_acudiente = st.text_input("Nombre acudiente")
            Direccion = st.text_input("Dirección")
            Cedula_acudiente = st.text_input("Cédula acudiente")
            Correo = st.text_input("Correo")
            Contacto = st.text_input("Contacto")

            submitted = st.form_submit_button("Agregar jugador")
            if submitted:
                fecha_str = Fecha_nac.isoformat() if Fecha_nac else ""
                player_data = {
                    "Nombres": Nombres.strip(),
                    "Apellidos": Apellidos.strip(),
                    "Documento": Documento.strip(),
                    "Fecha nacimiento": fecha_str,
                    "Categoría": Categoria,
                    "Nombre acudiente": Nombre_acudiente.strip(),
                    "Dirección": Direccion.strip(),
                    "Cédula acudiente": Cedula_acudiente.strip(),
                    "Correo": Correo.strip(),
                    "Contacto": Contacto.strip()
                }
                ok, msg = add_player_to_xls(xls, player_data)
                if ok:
                    # guardar y subir a Drive (file_id puede ser None y será creado)
                    file_id = save_excel_and_upload(xls, file_id)
                    st.success("✅ " + msg + " (subido a Drive).")
                else:
                    st.error(msg)

    st.markdown("---")
    st.subheader("Buscar / Eliminar jugadores")
    df_jug = xls["Jugadores"]
    if df_jug.empty:
        st.info("No hay jugadores registrados.")
    else:
        query = st.text_input("Buscar por nombre o documento")
        result = df_jug[df_jug.apply(lambda row: query.lower() in " ".join(map(str, row.values)).lower(), axis=1)] if query else df_jug
        st.dataframe(result)
        doc_to_delete = st.text_input("Documento a eliminar")
        if st.button("Eliminar jugador"):
            if doc_to_delete:
                # eliminar localmente
                df = xls["Jugadores"]
                if str(doc_to_delete) in df["Documento"].astype(str).values:
                    df = df[df["Documento"].astype(str) != str(doc_to_delete)]
                    xls["Jugadores"] = df
                    file_id = save_excel_and_upload(xls, file_id)
                    st.success("✅ Jugador eliminado y archivo actualizado.")
                else:
                    st.error("Documento no encontrado.")

# ---------- REGISTRAR PAGO ----------
elif menu == "💸 Registrar pago":
    st.header("💸 Registrar pago")
    tipo = st.selectbox("Tipo de pago", ["Mensualidad", "Uniforme", "Torneo"])

    if tipo == "Mensualidad":
        categoria = st.selectbox("Categoría", categorias)
        df_cat = xls.get(categoria, pd.DataFrame(columns=["Jugador"] + meses))
        if df_cat.empty:
            st.warning("No hay jugadores en esta categoría.")
        else:
            jugador = st.selectbox("Jugador", df_cat["Jugador"].tolist())
            mes = st.selectbox("Mes", meses)
            monto = st.number_input("Monto", min_value=0.0, step=1000.0)
            if st.button("Guardar mensualidad"):
                ok, msg = update_monthly_in_xls(xls, categoria, jugador, mes, monto)
                if ok:
                    file_id = save_excel_and_upload(xls, file_id)
                    st.success("✅ " + msg + " (subido a Drive).")
                else:
                    st.error(msg)

    elif tipo == "Uniforme":
        df_jug = xls["Jugadores"]
        jugadores_list = (df_jug["Nombres"].astype(str) + " " + df_jug["Apellidos"].astype(str)).tolist() if not df_jug.empty else []
        jugador = st.selectbox("Jugador", jugadores_list)
        categoria = st.selectbox("Categoría", categorias)
        fecha = st.date_input("Fecha")
        valor = st.number_input("Valor", min_value=0.0, step=1000.0)
        obs = st.text_input("Observaciones")
        if st.button("Registrar uniforme"):
            fecha_str = fecha.isoformat() if fecha else ""
            ok, msg = append_uniform_in_xls(xls, jugador, categoria, fecha_str, valor, obs)
            if ok:
                file_id = save_excel_and_upload(xls, file_id)
                st.success("✅ " + msg + " (subido a Drive).")
            else:
                st.error(msg)

    elif tipo == "Torneo":
        df_jug = xls["Jugadores"]
        jugadores_list = (df_jug["Nombres"].astype(str) + " " + df_jug["Apellidos"].astype(str)).tolist() if not df_jug.empty else []
        jugador = st.selectbox("Jugador", jugadores_list)
        categoria = st.selectbox("Categoría", categorias)
        nombre_torneo = st.text_input("Nombre Torneo")
        fecha = st.date_input("Fecha del torneo")
        valor = st.number_input("Valor", min_value=0.0, step=1000.0)
        obs = st.text_input("Observaciones")
        if st.button("Registrar torneo"):
            fecha_str = fecha.isoformat() if fecha else ""
            ok, msg = append_torneo_in_xls(xls, jugador, categoria, nombre_torneo, fecha_str, valor, obs)
            if ok:
                file_id = save_excel_and_upload(xls, file_id)
                st.success("✅ " + msg + " (subido a Drive).")
            else:
                st.error(msg)

# ---------- SINCRONIZAR / VER DATOS ----------
elif menu == "🔁 Sincronizar":
    st.header("🔁 Sincronizar / Forzar descarga desde Drive")
    if st.button("Descargar última versión desde Drive"):
        xls, file_id = load_excel_from_drive()
        st.success("✅ Archivo descargado y cargado en memoria.")
    st.markdown("---")
    st.subheader("Ver hojas")
    hoja = st.selectbox("Selecciona hoja", ["Jugadores"] + categorias + ["Uniformes", "Torneos"])
    st.dataframe(xls.get(hoja, pd.DataFrame({"Info": ["Hoja vacía"]})))

# ---------- VER DATOS ----------
elif menu == "📊 Ver datos":
    st.header("📊 Ver datos (hojas)")
    hoja = st.selectbox("Selecciona hoja para ver", ["Jugadores"] + categorias + ["Uniformes", "Torneos"])
    st.dataframe(xls.get(hoja, pd.DataFrame({"Info": ["No hay datos en esta hoja"]})))



   






