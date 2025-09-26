# app.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import gspread.exceptions

st.set_page_config(page_title="Pagos Escuela de Fútbol", layout="wide")

# ===============================
# 0️⃣  CONFIG - MESES Y CATEGORIAS
# ===============================
meses = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

categorias = [str(y) for y in range(2011, 2022)]  # 2011..2021

# ===============================
# 1️⃣  CONFIGURACIÓN GOOGLE SHEETS
# ===============================
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
]

creds_dict = st.secrets["gcp"]
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
client = gspread.authorize(creds)

SPREADSHEET_NAME = "Pagos"
spreadsheet = client.open(SPREADSHEET_NAME)

# ===============================
# 2️⃣  UTIL: crear/obtener hojas
# ===============================
def get_or_create_worksheet(name, header=None):
    """Obtiene la worksheet si existe, si no la crea y opcionalmente agrega header"""
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        # Crear hoja en blanco y añadir header si se da
        ws = spreadsheet.add_worksheet(title=name, rows="1000", cols="26")
        if header:
            ws.append_row(header)
    else:
        # si existe y header se pide y sheet vacía, aseguramos header
        if header:
            values = ws.get_all_values()
            if not values or len(values) == 0 or (len(values) == 1 and all([c == "" for c in values[0]])):
                ws.clear()
                ws.append_row(header)
    return ws

def ensure_all_sheets_exist():
    """Asegura que las hojas necesarias existan (vacías si es necesario)."""
    # Jugadores
    jugadores_header = ["Nombres", "Apellidos", "Documento", "Fecha nacimiento", "Categoría",
                        "Nombre acudiente", "Dirección", "Cédula acudiente", "Correo", "Contacto"]
    get_or_create_worksheet("Jugadores", header=jugadores_header)

    # Hojas por categoría: matriz de mensualidades: columna Jugador + meses
    cat_header = ["Jugador"] + meses
    for c in categorias:
        get_or_create_worksheet(c, header=cat_header)

    # Uniformes
    uniformes_header = ["Jugador", "Categoría", "Fecha", "Valor", "Observaciones"]
    get_or_create_worksheet("Uniformes", header=uniformes_header)

    # Torneos
    torneos_header = ["Jugador", "Categoría", "Nombre Torneo", "Fecha", "Valor", "Observaciones"]
    get_or_create_worksheet("Torneos", header=torneos_header)

# Llamada de inicialización
ensure_all_sheets_exist()

# ===============================
# 3️⃣  FUNCIONES DE LECTURA/ESCRITURA
# ===============================
def load_worksheet_as_df(sheet_name):
    ws = spreadsheet.worksheet(sheet_name)
    data = ws.get_all_records()
    return pd.DataFrame(data)

def append_row_to_sheet(sheet_name, row_dict, header_order=None):
    """Agrega una fila diccionario a la sheet, respetando header_order si se da."""
    ws = spreadsheet.worksheet(sheet_name)
    if header_order is None:
        header = ws.row_values(1)
    else:
        header = header_order
    # Construir fila en orden del header
    row = [row_dict.get(col, "") for col in header]
    ws.append_row(row)

def save_df_to_sheet(sheet_name, df):
    """Reemplaza el contenido de la hoja con el DataFrame (incluye header)."""
    ws = spreadsheet.worksheet(sheet_name)
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.values.tolist())

# ===============================
# 4️⃣  OPERACIONES: Jugadores
# ===============================
def add_player_record(player_data):
    """
    player_data: dict con claves:
      Nombres, Apellidos, Documento, Fecha nacimiento (YYYY-MM-DD o string),
      Categoría, Nombre acudiente, Dirección, Cédula acudiente, Correo, Contacto
    """
    # 1) Agregar a hoja Jugadores
    jugadores_header = ["Nombres", "Apellidos", "Documento", "Fecha nacimiento", "Categoría",
                        "Nombre acudiente", "Dirección", "Cédula acudiente", "Correo", "Contacto"]
    # Validación simple: documento requerido
    if not player_data.get("Documento"):
        return False, "El campo Documento es obligatorio."
    # Evitar duplicados por Documento
    df_jug = load_worksheet_as_df("Jugadores")
    if not df_jug.empty and player_data["Documento"] in df_jug["Documento"].astype(str).values:
        return False, "Ya existe un jugador con ese documento."

    append_row_to_sheet("Jugadores", player_data, header_order=jugadores_header)

    # 2) Agregar al sheet de la categoría: solo nombre completo en la columna Jugador
    categoria = player_data.get("Categoría")
    if categoria not in categorias:
        # si categoría no válida, no fallamos pero retornamos aviso
        return True, f"Jugador agregado a 'Jugadores' pero categoría '{categoria}' no válida. Revisa."
    cat_ws = spreadsheet.worksheet(categoria)
    # construir nombre completo
    nombre_completo = f"{player_data.get('Nombres','').strip()} {player_data.get('Apellidos','').strip()}".strip()
    # obtener header (esperamos "Jugador" + meses)
    header = cat_ws.row_values(1)
    if not header:
        header = ["Jugador"] + meses
        cat_ws.append_row(header)
    # Añadir fila con Jugador y ceros en meses
    row = [nombre_completo] + [0]*len(meses)
    cat_ws.append_row(row)
    return True, "Jugador agregado correctamente a 'Jugadores' y hoja de categoría."

def delete_player_by_document(documento):
    # Borrar de Jugadores
    ws = spreadsheet.worksheet("Jugadores")
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return False, "No hay jugadores registrados."
    if str(documento) not in df["Documento"].astype(str).values:
        return False, "Documento no encontrado."
    # fila index (1-based header)
    row_idx = df.index[df["Documento"].astype(str) == str(documento)][0] + 2
    ws.delete_rows(row_idx)
    # Opcional: borrar de la hoja de categoria (por nombre)
    return True, "Jugador eliminado de 'Jugadores'. **Revisa manualmente las hojas de categoría si deseas remover el nombre allí.**"

# ===============================
# 5️⃣  OPERACIONES: Pagos
# ===============================
def update_monthly_payment(categoria, jugador_nombre, mes, monto):
    """Actualiza el monto de un mes en la hoja de categoría (un solo valor por jugador/mes)."""
    if categoria not in categorias:
        return False, "Categoría inválida."
    ws = spreadsheet.worksheet(categoria)
    df = pd.DataFrame(ws.get_all_records())
    if df.empty:
        return False, "Hoja de categoría vacía."
    # Buscar jugador por coincidencia exacta
    mask = df["Jugador"].astype(str) == str(jugador_nombre)
    if not mask.any():
        return False, "Jugador no encontrado en la hoja de la categoría."
    df.loc[mask, mes] = monto
    save_df_to_sheet(categoria, df)
    return True, "Pago mensual actualizado."

def register_uniform(jugador, categoria, fecha, valor, observaciones=""):
    row = {
        "Jugador": jugador,
        "Categoría": categoria,
        "Fecha": fecha,
        "Valor": valor,
        "Observaciones": observaciones
    }
    append_row_to_sheet("Uniformes", row, header_order=["Jugador","Categoría","Fecha","Valor","Observaciones"])
    return True, "Registro de uniforme guardado."

def register_torneo(jugador, categoria, nombre_torneo, fecha, valor, observaciones=""):
    row = {
        "Jugador": jugador,
        "Categoría": categoria,
        "Nombre Torneo": nombre_torneo,
        "Fecha": fecha,
        "Valor": valor,
        "Observaciones": observaciones
    }
    append_row_to_sheet("Torneos", row, header_order=["Jugador","Categoría","Nombre Torneo","Fecha","Valor","Observaciones"])
    return True, "Registro de torneo guardado."

# ===============================
# 6️⃣  INTERFAZ STREAMLIT
# ===============================
st.title("⚽ Sistema de pagos - Escuela de Fútbol (Google Sheets)")

menu = st.sidebar.radio("📂 Navegación", ["👥 Gestión de jugadores", "💸 Registrar pago", "📊 Ver datos"])

# ---------- GESTIÓN DE JUGADORES ----------
if menu == "👥 Gestión de jugadores":
    st.header("👥 Gestión de jugadores")
    with st.expander("Agregar nuevo jugador"):
        with st.form("form_add_player"):
            Nombres = st.text_input("Nombres", "")
            Apellidos = st.text_input("Apellidos", "")
            Documento = st.text_input("Documento", "")
            Fecha_nac = st.date_input("Fecha de nacimiento", value=None)
            Categoria = st.selectbox("Categoría", categorias)
            Nombre_acudiente = st.text_input("Nombre acudiente", "")
            Direccion = st.text_input("Dirección", "")
            Cedula_acudiente = st.text_input("Cédula acudiente", "")
            Correo = st.text_input("Correo", "")
            Contacto = st.text_input("Contacto", "")

            submitted = st.form_submit_button("Agregar jugador")
            if submitted:
                # convertir fecha a string ISO si se eligió
                fecha_str = Fecha_nac.strftime("%Y-%m-%d") if isinstance(Fecha_nac, datetime) or Fecha_nac else ""
                if Fecha_nac and not isinstance(Fecha_nac, str):
                    fecha_str = Fecha_nac.isoformat()
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
                ok, msg = add_player_record(player_data)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    st.markdown("---")
    st.subheader("Buscar / Eliminar jugadores")
    df_jug = load_worksheet_as_df("Jugadores")
    if df_jug.empty:
        st.info("No hay jugadores registrados.")
    else:
        # mostrar tabla con búsqueda simple por documento o nombre
        query = st.text_input("Buscar por nombre o documento")
        if query:
            mask = df_jug.apply(lambda row: query.lower() in " ".join(map(str, row.values)).lower(), axis=1)
            result = df_jug[mask]
        else:
            result = df_jug
        st.dataframe(result)

        # Eliminar por documento
        st.write("Eliminar jugador (por Documento)")
        doc_to_delete = st.text_input("Documento a eliminar")
        if st.button("Eliminar jugador"):
            if doc_to_delete:
                ok, msg = delete_player_by_document(doc_to_delete.strip())
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.warning("Ingresa el documento a eliminar.")

# ---------- REGISTRAR PAGO ----------
elif menu == "💸 Registrar pago":
    st.header("💸 Registrar pago")
    tipo = st.selectbox("Tipo de pago", ["Mensualidad", "Uniforme", "Torneo"])

    if tipo == "Mensualidad":
        st.subheader("Registrar mensualidad (matriz)")
        categoria = st.selectbox("Categoría", categorias)
        df_cat = load_worksheet_as_df(categoria)
        if df_cat.empty:
            st.warning("No hay jugadores en esta categoría.")
        else:
            jugador = st.selectbox("Jugador", df_cat["Jugador"].tolist())
            mes = st.selectbox("Mes", meses)
            monto = st.number_input("Monto", min_value=0.0, step=1000.0)
            if st.button("Guardar mensualidad"):
                ok, msg = update_monthly_payment(categoria, jugador, mes, monto)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    elif tipo == "Uniforme":
        st.subheader("Registrar compra de uniforme")
        df_jug = load_worksheet_as_df("Jugadores")
        jugadores_list = (df_jug["Nombres"].astype(str) + " " + df_jug["Apellidos"].astype(str)).tolist() if not df_jug.empty else []
        jugador = st.selectbox("Jugador", jugadores_list)
        categoria = st.selectbox("Categoría", categorias)
        fecha = st.date_input("Fecha")
        valor = st.number_input("Valor", min_value=0.0, step=1000.0)
        obs = st.text_input("Observaciones (opcional)")
        if st.button("Registrar uniforme"):
            fecha_str = fecha.isoformat() if isinstance(fecha, datetime) or fecha else ""
            ok, msg = register_uniform(jugador, categoria, fecha_str, valor, obs)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    elif tipo == "Torneo":
        st.subheader("Registrar pago de torneo")
        df_jug = load_worksheet_as_df("Jugadores")
        jugadores_list = (df_jug["Nombres"].astype(str) + " " + df_jug["Apellidos"].astype(str)).tolist() if not df_jug.empty else []
        jugador = st.selectbox("Jugador", jugadores_list)
        categoria = st.selectbox("Categoría", categorias)
        nombre_torneo = st.text_input("Nombre Torneo")
        fecha = st.date_input("Fecha del torneo")
        valor = st.number_input("Valor", min_value=0.0, step=1000.0)
        obs = st.text_input("Observaciones (opcional)")
        if st.button("Registrar torneo"):
            fecha_str = fecha.isoformat() if isinstance(fecha, datetime) or fecha else ""
            ok, msg = register_torneo(jugador, categoria, nombre_torneo, fecha_str, valor, obs)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

# ---------- VER DATOS ----------
elif menu == "📊 Ver datos":
    st.header("📊 Ver datos (hojas)")
    hoja = st.selectbox("Selecciona hoja para ver", ["Jugadores"] + categorias + ["Uniformes", "Torneos"])
    df = load_worksheet_as_df(hoja)
    if df.empty:
        st.info("No hay datos para mostrar en esta hoja.")
    else:
        st.dataframe(df)
        # opción para descargar csv
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(label="Descargar CSV", data=csv, file_name=f"{hoja}.csv", mime="text/csv")
