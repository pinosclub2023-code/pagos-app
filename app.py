import streamlit as st
import pandas as pd
import os

# ---------------------------
# Config
# ---------------------------
CATEGORIES = ["sub11", "sub12", "sub13"]   # <-- si quieres agregar/quitar, edita esta lista
DATA_DIR = "data"
MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
          "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
JUGADORES_COL = "nombre"

# ---------------------------
# Utilidades de archivo
# ---------------------------
def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def category_path(cat):
    return os.path.join(DATA_DIR, f"{cat}.csv")

def create_empty_category_csv(cat):
    """Crea CSV con columnas: nombre + meses, sin filas."""
    df = pd.DataFrame(columns=[JUGADORES_COL] + MONTHS)
    df.to_csv(category_path(cat), index=False)

def load_category(cat):
    path = category_path(cat)
    if not os.path.exists(path):
        create_empty_category_csv(cat)
    df = pd.read_csv(path, dtype=str)  # leemos como string para evitar problemas
    # Asegurarnos de que están todas las columnas
    for m in MONTHS:
        if m not in df.columns:
            df[m] = "0"
    if JUGADORES_COL not in df.columns:
        df[JUGADORES_COL] = ""
    # Normalizar: si hay NaN
    df = df.fillna("0")
    # Mantener 'nombre' al inicio
    cols = [JUGADORES_COL] + [c for c in df.columns if c != JUGADORES_COL]
    return df[cols]

def save_category(cat, df):
    df.to_csv(category_path(cat), index=False)

def add_player(cat, nombre):
    df = load_category(cat)
    nombre = nombre.strip()
    if nombre == "":
        return False, "El nombre está vacío."
    # Evitar duplicados exactos (ignorando mayúsculas/minúsculas)
    if any(df[JUGADORES_COL].str.lower() == nombre.lower()):
        return False, "El jugador ya existe en esta categoría."
    new_row = {JUGADORES_COL: nombre}
    for m in MONTHS:
        new_row[m] = "0"
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    save_category(cat, df)
    return True, "Jugador agregado."

def delete_player(cat, nombre):
    df = load_category(cat)
    mask = df[JUGADORES_COL].str.lower() == nombre.lower()
    if not mask.any():
        return False, "Jugador no encontrado."
    df = df[~mask]
    save_category(cat, df)
    return True, "Jugador eliminado."

def update_payment(cat, nombre, mes, monto):
    df = load_category(cat)
    # Buscar fila por nombre (case-insensitive)
    idx = df[df[JUGADORES_COL].str.lower() == nombre.lower()].index
    if len(idx) == 0:
        return False, "Jugador no encontrado."
    # Validar monto (aceptar números o vacíos)
    monto_str = str(monto).strip()
    if monto_str == "":
        monto_str = "0"
    # Reemplazar comas por nada y puntos por nada (por si ponen 50.000) -> guardamos sin formato
    monto_str = monto_str.replace(".", "").replace(",", "")
    # Validación básica: debe quedar un número entero o 0
    if not monto_str.isdigit():
        return False, "Monto inválido. Usa solo números (ej. 50000)."
    df.at[idx[0], mes] = monto_str
    save_category(cat, df)
    return True, "Pago registrado."

# ---------------------------
# UI con Streamlit
# ---------------------------
st.set_page_config(page_title="Pagos - Escuela de Fútbol", layout="wide")

st.title("📋 Sistema de pagos - Escuela de Fútbol (versión local, CSV)")

ensure_data_dir()

# Sidebar: selección de categoría y navegación
st.sidebar.header("Configuración")
selected_cat = st.sidebar.selectbox("Elige la categoría", CATEGORIES)

st.sidebar.markdown("### Navegación")
page = st.sidebar.radio("", ["Gestión de jugadores", "Registrar pago", "Ver pagos", "Exportar / Backup"])

# ---------------------------
# Página: Gestión de jugadores
# ---------------------------
if page == "Gestión de jugadores":
    st.header("👥 Gestión de jugadores")
    st.markdown(f"Categoría seleccionada: **{selected_cat}**")
    df = load_category(selected_cat)

    # Formulario para agregar jugador
    st.subheader("➕ Agregar jugador")
    with st.form("form_add"):
        new_name = st.text_input("Nombre completo")
        submitted = st.form_submit_button("Agregar")
        if submitted:
            ok, msg = add_player(selected_cat, new_name)
            if ok:
                st.success(msg)
                df = load_category(selected_cat)
            else:
                st.error(msg)

    # Eliminar jugador
    st.subheader("🗑️ Eliminar jugador")
    if df.empty:
        st.info("No hay jugadores registrados en esta categoría.")
    else:
        names = df[JUGADORES_COL].tolist()
        to_delete = st.selectbox("Selecciona jugador para eliminar", [""] + names)
        if to_delete != "":
            if st.button("Eliminar jugador"):
                ok, msg = delete_player(selected_cat, to_delete)
                if ok:
                    st.success(msg)
                    df = load_category(selected_cat)
                else:
                    st.error(msg)

    # Mostrar tabla de jugadores
    st.subheader("Lista de jugadores (matriz de pagos)")
    st.dataframe(df.rename(columns=lambda x: x))  # streamlit-friendly

# ---------------------------
# Página: Registrar pago
# ---------------------------
elif page == "Registrar pago":
    st.header("💳 Registrar / Actualizar pago")
    st.markdown(f"Categoría seleccionada: **{selected_cat}**")
    df = load_category(selected_cat)

    if df.empty:
        st.info("No hay jugadores en esta categoría. Primero agrega jugadores en 'Gestión de jugadores'.")
    else:
        names = df[JUGADORES_COL].tolist()
        with st.form("form_payment"):
            player = st.selectbox("Jugador", names)
            month = st.selectbox("Mes", MONTHS)
            monto = st.text_input("Monto (ej. 50000)")
            st.markdown("Si dejas el monto vacío o pones 0, quedará como 0.")
            submitted = st.form_submit_button("Guardar pago")
            if submitted:
                ok, msg = update_payment(selected_cat, player, month, monto)
                if ok:
                    st.success(msg)
                    df = load_category(selected_cat)
                else:
                    st.error(msg)

        # Mostrar la fila del jugador para ver lo que quedó
        st.subheader("Registro del jugador seleccionado")
        st.table(df[df[JUGADORES_COL].str.lower() == player.lower()])

# ---------------------------
# Página: Ver pagos
# ---------------------------
elif page == "Ver pagos":
    st.header("📊 Ver pagos y filtrar")
    df = load_category(selected_cat)
    if df.empty:
        st.info("No hay datos para mostrar en esta categoría.")
    else:
        col1, col2 = st.columns([2, 1])
        with col1:
            search_name = st.text_input("Buscar jugador (nombre)")
            month_filter = st.selectbox("Filtrar por mes (opcional)", ["Todos"] + MONTHS)
        with col2:
            show_only_debtors = st.checkbox("Mostrar solo que deben (monto = 0)", value=False)

        df_show = df.copy()
        if search_name.strip() != "":
            df_show = df_show[df_show[JUGADORES_COL].str.contains(search_name, case=False, na=False)]

        if month_filter != "Todos":
            # Mostrar solo columnas nombre + el mes seleccionado
            df_show = df_show[[JUGADORES_COL, month_filter]]

        if show_only_debtors:
            if month_filter == "Todos":
                # Mostrar jugadores que tienen 0 en algún mes (o en todos)
                mask = (df_show[MONTHS] == "0").any(axis=1)
                df_show = df_show[mask]
            else:
                df_show = df_show[df_show[month_filter] == "0"]

        st.dataframe(df_show)

        # Resumen rápido: totales por mes (sumando montos como ints)
        st.subheader("Resumen: ingresos por mes (esta categoría)")
        sums = {}
        for m in MONTHS:
            # convertir a int; si hay strings vacíos o no-numéricos, tratarlos como 0
            s = pd.to_numeric(df[m].replace("", "0").astype(str).str.replace(".", "").str.replace(",", ""), errors='coerce').fillna(0).astype(int).sum()
            sums[m] = s
        sums_df = pd.DataFrame(list(sums.items()), columns=["Mes", "Total recaudado"])
        st.table(sums_df)

# ---------------------------
# Página: Exportar / Backup
# ---------------------------
elif page == "Exportar / Backup":
    st.header("💾 Exportar / Backup")
    st.markdown("Puedes descargar el CSV de la categoría actual o crear un backup de todos los CSV en la carpeta `data/`.")

    df = load_category(selected_cat)
    if not df.empty:
        st.download_button("📥 Descargar CSV de categoría actual", data=df.to_csv(index=False).encode('utf-8'), file_name=f"{selected_cat}.csv", mime="text/csv")

    if st.button("Crear backup (todos los CSV → zip)"):
        import zipfile, io
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            for cat in CATEGORIES:
                p = category_path(cat)
                if os.path.exists(p):
                    z.write(p, arcname=os.path.basename(p))
        buffer.seek(0)
        st.download_button("📥 Descargar backup (zip)", data=buffer, file_name="backup_csvs.zip", mime="application/zip")

st.sidebar.markdown("---")
st.sidebar.markdown("Hecho con ❤️ — si quieres que lo conecte a Google Sheets después, lo hago fácil.")

