"""
UI de Streamlit: filtros de búsqueda, las 4 pestañas del flujo (Búsqueda,
Datos limpios, Enriquecimiento, Monday) y los componentes de gestión de
contacto. La lógica de cada integración externa vive en su propio módulo
(denue.py, enrichment.py, hunter.py, monday.py) — acá solo se orquesta.
"""
import pandas as pd
import requests
import streamlit as st

from catalogos import ENTIDADES_FEDERATIVAS, SECTOR_TODOS, SECTORES_SCIAN
from config import (
    ANTHROPIC_API_KEY,
    API_KEY,
    COLUMN_CONFIG,
    COLUMNAS_CONTACTO_GESTION,
    COLUMNAS_CONTACTO_INTERNAS,
    COLUMNAS_CONTACTO_MONDAY,
    COLUMNAS_ENRIQUECIMIENTO,
    COLUMNAS_LIMPIAS,
    ENTIDAD_TODOS,
    ESTRATO_TODOS,
    HUNTER_API_KEY,
    MONDAY_API_KEY,
    MONDAY_BOARD_CUENTAS,
    N_EMPRESAS_ENRIQUECER,
    ROLES_CONTACTO,
    SERPAPI_KEY,
    TAMANO_PAGINA,
    TODOS_LOS_ROLES,
)
from cuentas import (
    clasificar_cuentas,
    monday_crear_cuenta,
    monday_listar_cuentas_reales,
    perfil_desde_cuenta,
)
from denue import agrupar_por_empresa, buscar_denue, marcar_grupo_corporativo
from enrichment import _dedup_contactos, buscar_contacto_por_rol, enriquecer_empresa, roles_a_buscar
from hunter import (
    calcular_score_correo,
    hunter_buscar_email,
    hunter_correos_del_dominio,
    hunter_enriquecimiento_combinado,
    hunter_verificar_email,
)
from monday import monday_correo_existe, monday_crear_contacto, monday_listar_usuarios
from utils import (
    _gmail_compose_url,
    _texto,
    _valor_valido,
    dominio_de_empresa,
    es_correo_general,
    extraer_dominio,
    fila_contacto,
    sitio_web_valido,
)

st.set_page_config(
    page_title="Explorador DENUE",
    page_icon=":material/storefront:",
    layout="wide",
)


@st.dialog("Confirmar exportación a Monday")
def dialog_exportar_monday(idx, etiqueta, cuenta, responsable_id):
    st.write(f"¿Seguro que querés exportar a **{etiqueta}** ({cuenta}) a Monday?")
    col_si, col_no = st.columns(2)
    with col_si:
        if st.button("Sí, exportar", key=f"dialog_si_{idx}", type="primary"):
            fila = st.session_state["df_contactos"].loc[idx]
            try:
                if _valor_valido(fila["Correo"]) and monday_correo_existe(fila["Correo"]):
                    st.session_state["_monday_aviso"] = (
                        "warning", f"{etiqueta} ya existe en Monday (mismo correo) — no se duplica."
                    )
                else:
                    cuenta_item_id = fila["Cuenta item id"]
                    if not _valor_valido(cuenta_item_id):
                        cuenta_item_id = monday_crear_cuenta(fila)
                        # Propaga el id nuevo a TODAS las filas de la misma cuenta (una
                        # por candidato de contacto, ver fila_contacto en utils.py) — no
                        # solo a `idx` — para no crear una cuenta duplicada en Monday
                        # cuando se exporte un segundo contacto de la misma empresa.
                        mismo_nombre = (
                            st.session_state["df_contactos"]["Cuenta asociada"] == fila["Cuenta asociada"]
                        )
                        st.session_state["df_contactos"].loc[mismo_nombre, "Cuenta item id"] = cuenta_item_id
                    monday_crear_contacto(fila, cuenta_item_id, responsable_id=responsable_id)
                    st.session_state["_monday_aviso"] = ("success", f"{etiqueta} exportado correctamente.")
                st.session_state["df_contactos"].loc[idx, "Exportado a Monday"] = True
            except Exception as exc:
                st.session_state["_monday_aviso"] = ("error", f"{etiqueta} — error al exportar: {exc}")
            st.rerun()
    with col_no:
        if st.button("Cancelar", key=f"dialog_no_{idx}"):
            st.rerun()


def _renderizar_tarjeta_contacto(idx, fila, usuarios_monday):
    """Una tarjeta por contacto. El contenido de abajo (gestión vs. resumen
    de solo lectura) depende de si ya se exportó o se marcó como inexistente
    — separa las 3 categorías de la pestaña Monday en un solo lugar."""
    etiqueta = _texto(fila["Nombre"], "Contacto sin nombre")
    exportado = bool(fila["Exportado a Monday"])
    marcado_no_existe = bool(fila["No existe / desvinculado"])

    with st.container(border=True):
        col_info, col_correo, col_linkedin = st.columns([2.6, 1.2, 1.2])
        with col_info:
            st.markdown(f"#### {etiqueta}")
            subtitulo = " · ".join(
                t for t in (
                    _texto(fila["Cuenta asociada"], ""),
                    _texto(fila["Nivel de cargo"], ""),
                    _texto(fila["Nombre de cargo"], ""),
                ) if t
            )
            if subtitulo:
                st.caption(subtitulo)
            if _valor_valido(fila["Correo"]):
                st.caption(fila["Correo"])
        with col_correo:
            if _valor_valido(fila["Correo"]):
                st.link_button(
                    "Enviar correo", _gmail_compose_url(fila["Correo"]),
                    icon=":material/mail:", use_container_width=True,
                )
            else:
                st.caption("Sin correo")
        with col_linkedin:
            if _valor_valido(fila["Link de LinkedIn"]):
                st.link_button(
                    "Ver LinkedIn", fila["Link de LinkedIn"],
                    icon=":material/open_in_new:", use_container_width=True,
                )
            else:
                st.caption("Sin LinkedIn")

        st.divider()

        if exportado:
            st.success("Ya exportado a Monday", icon=":material/check_circle:")
        elif marcado_no_existe:
            st.caption("Marcado como no existente / desvinculado — no se exporta.")
            if st.button("Reactivar", key=f"reactivar_{idx}", icon=":material/restart_alt:"):
                st.session_state["df_contactos"].loc[idx, "No existe / desvinculado"] = False
                st.rerun()
        else:
            col_resp, col_contactado, col_no_existe, col_exportar = st.columns([2, 1.3, 1.8, 1.8])
            with col_resp:
                responsable_nombre = st.selectbox(
                    "Responsable", options=[""] + list(usuarios_monday.keys()), key=f"responsable_{idx}",
                )
            with col_contactado:
                contactado = st.checkbox(
                    "Contactado", value=bool(fila["Contactado"]), key=f"contactado_{idx}"
                )
            with col_no_existe:
                marcar_no_existe = st.checkbox(
                    "No existe / desvinculado", value=False, key=f"no_existe_{idx}"
                )
            st.session_state["df_contactos"].loc[idx, "Contactado"] = contactado
            st.session_state["df_contactos"].loc[idx, "No existe / desvinculado"] = marcar_no_existe
            with col_exportar:
                st.write("")
                if st.button(
                    "Exportar a Monday", key=f"exportar_{idx}",
                    disabled=(not contactado) or marcar_no_existe,
                    icon=":material/cloud_upload:", use_container_width=True,
                ):
                    dialog_exportar_monday(
                        idx, etiqueta, fila["Cuenta asociada"], usuarios_monday.get(responsable_nombre)
                    )


st.title("Explorador DENUE")
st.caption("Consulta y filtra el Directorio Estadístico Nacional de Unidades Económicas (INEGI).")

if not API_KEY:
    st.error("No se encontró DENUE_API_KEY en el archivo .env.")
    st.stop()

with st.sidebar:
    st.header("Filtros")
    with st.form("filtros_form"):
        sector_options = [SECTOR_TODOS] + list(SECTORES_SCIAN.keys())
        sector_labels = {SECTOR_TODOS: "Todos los sectores", **SECTORES_SCIAN}
        sector = st.selectbox(
            "Sector económico (SCIAN)",
            options=sector_options,
            format_func=lambda code: f"{code} — {sector_labels[code]}" if code != SECTOR_TODOS else sector_labels[code],
        )

        entidad_options = [ENTIDAD_TODOS] + list(ENTIDADES_FEDERATIVAS.keys())
        entidad_labels = {ENTIDAD_TODOS: "Todo el país", **ENTIDADES_FEDERATIVAS}
        entidad = st.selectbox(
            "Estado",
            options=entidad_options,
            format_func=lambda code: entidad_labels[code],
        )

        nombre = st.text_input(
            "Palabra clave (nombre del negocio)",
            placeholder="Vacío = todos",
        )

        st.caption(
            "Trae todos los registros disponibles para el sector/estado elegido "
            "(sin tope), en páginas de 5,000. Puede tardar si el universo es grande."
        )

        buscar = st.form_submit_button("Buscar", icon=":material/search:")

if buscar:
    st.session_state["ultima_busqueda"] = {
        "entidad": entidad,
        "sector": sector,
        "nombre": nombre,
    }

busqueda = st.session_state.get("ultima_busqueda")

if not busqueda:
    st.info("Configurá los filtros en la barra lateral y presioná **Buscar**.")
    st.stop()

try:
    dfs_paginas = []
    regini = 1
    pagina = 1
    ultima_url = None
    corte_anormal = False
    with st.status("Descargando registros del DENUE...", expanded=True) as status:
        while True:
            regfin = regini + TAMANO_PAGINA - 1
            status.update(label=f"Página {pagina} — registros {regini} a {regfin}...")
            try:
                df_pagina, ultima_url = buscar_denue(
                    busqueda["entidad"],
                    busqueda["sector"],
                    ESTRATO_TODOS,
                    busqueda["nombre"],
                    regini,
                    regfin,
                    API_KEY,
                )
            except requests.exceptions.RequestException:
                # La API del DENUE responde con un HTTP corrupto (en vez de una
                # lista vacía) cuando se piden páginas más allá del último
                # registro disponible. Si ya trajimos algo, lo tratamos como
                # fin de los datos en vez de descartar todo lo acumulado.
                if dfs_paginas:
                    corte_anormal = True
                    break
                raise
            if df_pagina.empty:
                break
            dfs_paginas.append(df_pagina)
            total_hasta_ahora = sum(len(p) for p in dfs_paginas)
            st.write(f"Página {pagina}: {len(df_pagina)} registros (acumulado: {total_hasta_ahora})")
            if len(df_pagina) < TAMANO_PAGINA:
                break
            regini += TAMANO_PAGINA
            pagina += 1
        total_final = sum(len(p) for p in dfs_paginas)
        if corte_anormal:
            status.update(
                label=f"Listo — {total_final} registros (corte al final de los disponibles)",
                state="complete",
            )
        else:
            status.update(label=f"Listo — {total_final} registros en total", state="complete")
    df = pd.concat(dfs_paginas, ignore_index=True) if dfs_paginas else pd.DataFrame()
    url_usada = ultima_url
except requests.exceptions.RequestException as exc:
    st.error(f"Error de conexión con la API del DENUE: {exc}")
    st.stop()
except ValueError as exc:
    st.error(f"La API respondió con un error: {exc}")
    st.stop()

if df.empty:
    st.warning("La búsqueda no arrojó resultados. Probá con otros filtros.")
    st.stop()

tab_busqueda, tab_limpios, tab_enriquecimiento, tab_monday = st.tabs(
    ["Búsqueda", "Datos limpios", "Enriquecimiento", "Monday"]
)

with tab_busqueda:
    st.metric("Establecimientos encontrados", len(df), border=True)

    st.dataframe(df, column_config=COLUMN_CONFIG, hide_index=True)

    st.download_button(
        "Descargar CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="denue_resultados.csv",
        mime="text/csv",
        icon=":material/download:",
    )

    with st.expander("Detalles de la consulta"):
        token_oculto = API_KEY[:4] + "…" + API_KEY[-4:]
        st.code(url_usada.replace(API_KEY, token_oculto), language="text")

with tab_limpios:
    st.caption(
        "Vas angostando los resultados en etapas para ver qué se descarta en cada una "
        "y qué queda como dato útil para el flujo de contacto B2B."
    )

    df_etapa1 = df.copy()

    with st.container(border=True):
        st.markdown("**Etapa 1 — Datos extraídos**")
        st.caption("Todas las sucursales encontradas, sin agrupar todavía.")

    # Agrupación por empresa: se calcula de fondo (el DENUE mide personal por
    # sucursal, no por empresa) pero no se muestra como paso — ver Etapa 2.
    df_etapa2 = agrupar_por_empresa(df_etapa1).sort_values("Personal_min", ascending=False)
    df_etapa2 = marcar_grupo_corporativo(df_etapa2)

    with st.container(border=True):
        st.markdown("**Etapa 2 — Filtro por cantidad mínima de empleados**")
        st.caption(
            "Sobre el personal total por empresa (sumando todas sus sucursales), "
            "ordenado de mayor a menor cantidad de empleados estimados."
        )
        minimo_empleados = st.number_input(
            "Cantidad mínima de empleados estimados",
            min_value=0,
            value=0,
            step=10,
            key="minimo_empleados",
        )
        df_etapa3 = df_etapa2[df_etapa2["Personal_min"] >= minimo_empleados]
        st.caption("Hacé click en una empresa para ver sus sucursales agrupadas.")
        evento_etapa2 = st.dataframe(
            df_etapa3[["Razon_social", "Sucursales", "Personal_estimado", "Banda_total"]],
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_etapa2",
        )
        filas_seleccionadas = evento_etapa2.selection.rows
        if filas_seleccionadas:
            empresa_seleccionada = df_etapa3.iloc[filas_seleccionadas[0]]
            razon_social_normalizada = str(empresa_seleccionada["Razon_social"]).strip()
            sucursales = df_etapa1[
                df_etapa1["Razon_social"].astype(str).str.strip() == razon_social_normalizada
            ]
            with st.expander(f"Sucursales de {empresa_seleccionada['Razon_social']}", expanded=True):
                st.dataframe(
                    sucursales[["Nombre", "Ubicacion", "Estrato", "Telefono", "Correo_e"]],
                    hide_index=True,
                )

    cuentas_reales = {}
    with st.container(border=True):
        st.markdown("**Etapa 3 — Clasificación contra el board de Cuentas**")
        if not MONDAY_API_KEY or not MONDAY_BOARD_CUENTAS:
            st.warning(
                "Falta MONDAY_API_KEY en el .env, o MONDAY_BOARD_CUENTAS no está "
                "configurado en config.py, para comparar contra Monday."
            )
            df_etapa4 = df_etapa3.copy()
            df_etapa4["Cuenta_item_id"] = None
        else:
            if st.button("Actualizar cuentas de Monday", icon=":material/refresh:"):
                monday_listar_cuentas_reales.clear()
            try:
                cuentas_reales = monday_listar_cuentas_reales()
                st.caption(f"{len(cuentas_reales)} cuenta(s) ya cargadas en Monday (board de Cuentas).")
                df_nueva, df_existe_necesita_contacto, df_existe_gestionada = clasificar_cuentas(
                    df_etapa3, cuentas_reales
                )
                df_etapa4 = pd.concat([df_nueva, df_existe_necesita_contacto])
                if not df_existe_gestionada.empty:
                    with st.expander(
                        f"Ver {len(df_existe_gestionada)} empresa(s) descartadas — ya tienen convenio o "
                        "contacto exitoso en Monday"
                    ):
                        st.dataframe(
                            df_existe_gestionada[["Razon_social", "Sucursales", "Personal_estimado", "Banda_total"]],
                            hide_index=True,
                        )
                if not df_existe_necesita_contacto.empty:
                    st.caption(
                        f"{len(df_existe_necesita_contacto)} empresa(s) ya existen en Monday pero sin "
                        "convenio ni contacto exitoso — se les busca contacto sin re-enriquecer perfil."
                    )
            except Exception as exc:
                st.error(f"No se pudo consultar Monday: {exc}")
                df_etapa4 = df_etapa3.copy()
                df_etapa4["Cuenta_item_id"] = None

    df_final_cols = [c for c in COLUMNAS_LIMPIAS if c in df_etapa4.columns]
    df_final = df_etapa4[df_final_cols].rename(columns=COLUMNAS_LIMPIAS)

    with st.container(horizontal=True):
        st.metric("Extraído (sucursales)", len(df_etapa1), border=True)
        st.metric("Agrupado (empresas)", len(df_etapa2), border=True)
        st.metric(
            "Tras filtro empleados",
            len(df_etapa3),
            delta=f"-{len(df_etapa2) - len(df_etapa3)}",
            delta_color="off",
            border=True,
        )
        st.metric(
            "Tras clasificación",
            len(df_etapa4),
            delta=f"-{len(df_etapa3) - len(df_etapa4)}",
            delta_color="off",
            border=True,
        )
        st.metric("Final limpio", len(df_final), border=True)

    with st.container(border=True):
        st.markdown("**Etapa 4 — Datos limpios finales**")
        if df_final.empty:
            st.warning("No quedaron empresas después de los filtros anteriores.")
        else:
            st.dataframe(df_final, hide_index=True)
            st.download_button(
                "Descargar datos limpios (CSV)",
                data=df_final.to_csv(index=False).encode("utf-8-sig"),
                file_name="denue_limpio.csv",
                mime="text/csv",
                icon=":material/download:",
            )

with tab_enriquecimiento:
    df_nueva_etapa4 = df_etapa4[df_etapa4["Cuenta_item_id"].isna()]
    df_existe_etapa4 = df_etapa4[df_etapa4["Cuenta_item_id"].notna()]
    candidatas_nuevas = df_nueva_etapa4.head(N_EMPRESAS_ENRIQUECER)

    _texto_cantidad = (
        "solo la empresa nueva con más personal estimado"
        if N_EMPRESAS_ENRIQUECER == 1
        else f"solo las primeras {N_EMPRESAS_ENRIQUECER} empresas nuevas de más personal estimado"
    )
    st.caption(
        f"Prototipo: busca y analiza {_texto_cantidad} de \"Datos limpios\", para no "
        "consumir de más las búsquedas de SerpAPI/Anthropic. Las empresas que ya existen "
        "en Monday (sin convenio ni contacto exitoso) no se re-enriquecen — usan el perfil "
        "que ya está cargado en el board de Cuentas."
    )
    st.caption(
        "**Personal estimado (DENUE)** vs. **Empleados (LinkedIn/web)** miden cosas distintas: "
        "el del DENUE es la presencia física detectada en el sector/estado que buscaste (y "
        "subestima cuando hay sucursales en la banda abierta '251 y más'); el de LinkedIn es lo "
        "que la empresa reporta a nivel global, autoreportado y sin auditar. No uses uno para "
        "reemplazar al otro — mostralos juntos y priorizá con criterio."
    )

    if not SERPAPI_KEY or not ANTHROPIC_API_KEY:
        st.warning("Faltan SERPAPI_KEY y/o ANTHROPIC_API_KEY en el .env para usar esta pestaña.")
    elif df_etapa4.empty:
        st.info("No hay empresas en 'Datos limpios' para enriquecer todavía.")
    else:
        st.caption(
            "Campos que se van a completar con la búsqueda (empresas nuevas): "
            + ", ".join(COLUMNAS_ENRIQUECIMIENTO.values()) + "."
        )
        st.markdown("**Datos actuales antes de enriquecer**")
        st.dataframe(df_final.head(N_EMPRESAS_ENRIQUECER), hide_index=True)
        if not df_existe_etapa4.empty:
            # Este grupo NO tiene tope (a diferencia de candidatas_nuevas, capado por
            # N_EMPRESAS_ENRIQUECER) — es intencional: el objetivo de esta funcionalidad
            # es justamente no perder oportunidades de búsqueda de contacto para cuentas
            # que ya existen en Monday pero todavía no están gestionadas. Como sí entran
            # de lleno al paso "Verificar y buscar contactos" (Hunter/SerpAPI/Claude), un
            # lote grande puede disparar muchas llamadas a esas APIs — se avisa con
            # st.warning en vez de st.caption a partir de 10 empresas (umbral arbitrario:
            # suficiente para no molestar en pruebas chicas, bajo para importar en serio).
            UMBRAL_AVISO_COSTO = 10
            _mensaje_existe = (
                f"{len(df_existe_etapa4)} empresa(s) ya existen en Monday — se procesan igual, "
                "sin re-enriquecer perfil."
            )
            if len(df_existe_etapa4) > UMBRAL_AVISO_COSTO:
                st.warning(
                    _mensaje_existe + " Al no tener tope, esto puede disparar muchas "
                    "llamadas a Hunter/SerpAPI/Claude en el paso 'Verificar y buscar "
                    "contactos' más abajo."
                )
            else:
                st.caption(_mensaje_existe)

        if st.button("Enriquecer estas empresas", icon=":material/travel_explore:"):
            resultados_nuevas = []
            with st.status("Enriqueciendo empresas...", expanded=True) as status:
                for i, fila in enumerate(candidatas_nuevas.itertuples(), start=1):
                    status.update(label=f"Empresa {i} de {len(candidatas_nuevas)} — {fila.Razon_social}...")
                    try:
                        resultado = enriquecer_empresa(
                            fila.Razon_social,
                            fila.Clase_actividad,
                            fila.Ubicacion,
                            SERPAPI_KEY,
                            ANTHROPIC_API_KEY,
                        )
                        resultados_nuevas.append(resultado.model_dump())
                        st.write(f"✓ {fila.Razon_social} — coincidencia {resultado.confianza_coincidencia}")
                    except Exception as exc:
                        resultados_nuevas.append(None)
                        st.write(f"✗ {fila.Razon_social} — error: {exc}")

                resultados_existe = []
                for fila in df_existe_etapa4.itertuples():
                    cuenta_monday = cuentas_reales.get(str(fila.Razon_social).strip().lower())
                    if cuenta_monday:
                        resultados_existe.append(perfil_desde_cuenta(cuenta_monday))
                        st.write(f"✓ {fila.Razon_social} — perfil tomado de Monday (cuenta existente)")
                    else:
                        resultados_existe.append(None)
                        st.write(f"✗ {fila.Razon_social} — no se encontró el registro de Monday (inesperado)")
                status.update(label="Enriquecimiento completo", state="complete")

            bloques = []
            for indice_grupo, resultados in (
                (candidatas_nuevas.index, resultados_nuevas),
                (df_existe_etapa4.index, resultados_existe),
            ):
                validas = [(idx, r) for idx, r in zip(indice_grupo, resultados) if r is not None]
                if not validas:
                    continue
                indices_validos, datos = zip(*validas)
                base = df_final.loc[list(indices_validos)].reset_index(drop=True)
                base["Cuenta_item_id"] = df_etapa4.loc[list(indices_validos), "Cuenta_item_id"].values
                enriquecido = pd.DataFrame(list(datos)).rename(columns=COLUMNAS_ENRIQUECIMIENTO)
                bloques.append(pd.concat([base, enriquecido], axis=1))

            if bloques:
                df_combinado = pd.concat(bloques, ignore_index=True)

                # El sitio del DENUE puede estar vacío o desactualizado (dominio que ya
                # no responde). Si no pasa el chequeo directo, se trata como si no
                # existiera y se completa con el que encontró la búsqueda de SerpAPI
                # (o el de Monday, para cuentas existentes — viaja en la misma columna).
                sitios_finales, fuentes_sitio = [], []
                for _, fila_sitio in df_combinado.iterrows():
                    sitio_denue = str(fila_sitio.get("Sitio web") or "").strip()
                    sitio_serpapi = str(fila_sitio.get("Sitio web (SerpAPI)") or "").strip()
                    if sitio_denue and sitio_web_valido(sitio_denue):
                        sitios_finales.append(sitio_denue)
                        fuentes_sitio.append("DENUE")
                    elif sitio_serpapi:
                        sitios_finales.append(sitio_serpapi)
                        fuentes_sitio.append(
                            "SerpAPI/Monday (DENUE vacío)" if not sitio_denue else "SerpAPI/Monday (el del DENUE no responde)"
                        )
                    else:
                        sitios_finales.append("")
                        fuentes_sitio.append("Sin sitio verificado")
                df_combinado["Sitio web"] = sitios_finales
                df_combinado["Fuente sitio web"] = fuentes_sitio

                st.session_state["df_enriquecido"] = df_combinado

        if "df_enriquecido" in st.session_state:
            st.dataframe(st.session_state["df_enriquecido"], hide_index=True)
            st.download_button(
                "Descargar enriquecimiento (CSV)",
                data=st.session_state["df_enriquecido"].to_csv(index=False).encode("utf-8-sig"),
                file_name="denue_enriquecido.csv",
                mime="text/csv",
                icon=":material/download:",
            )

            st.divider()
            st.subheader("Validación y contacto (Hunter)")
            if not HUNTER_API_KEY:
                st.warning("Falta HUNTER_API_KEY en el .env para esta sección.")
            else:
                df_base = st.session_state["df_enriquecido"]
                correo_col = df_base["Correo"].astype(str).str.strip()
                grupo_a = df_base[(correo_col != "") & (correo_col.str.lower() != "nan")]
                grupo_b = df_base[~df_base.index.isin(grupo_a.index)]

                st.caption(
                    f"Grupo A — ya tienen correo ({len(grupo_a)}): se verifica y se busca quién lo usa "
                    "(con respaldo de búsqueda por rol si Hunter no identifica a nadie). "
                    f"Grupo B — sin correo ({len(grupo_b)}): se busca a la persona del rol elegido y se "
                    "estima su correo. Un solo click procesa ambos grupos."
                )
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**Grupo A ({len(grupo_a)})**")
                    if not grupo_a.empty:
                        st.dataframe(grupo_a[["Razón social", "Correo"]], hide_index=True)
                with col_b:
                    st.markdown(f"**Grupo B ({len(grupo_b)})**")
                    if not grupo_b.empty:
                        st.dataframe(grupo_b[["Razón social", "Sitio web"]], hide_index=True)

                rol_elegido = None
                if not grupo_a.empty or not grupo_b.empty:
                    rol_elegido = st.selectbox(
                        "Rol a buscar (Grupo B, y respaldo para Grupo A si Hunter no identifica a nadie)",
                        options=[TODOS_LOS_ROLES] + list(ROLES_CONTACTO.keys()),
                    )
                    if rol_elegido == TODOS_LOS_ROLES:
                        st.caption(
                            "Busca los 4 roles para cada empresa — multiplica las búsquedas de "
                            "SerpAPI/Anthropic por empresa. Usar con pocas empresas a la vez."
                        )
                verificar = st.button("Verificar y buscar contactos", icon=":material/verified:")

                if verificar:
                    roles_seleccionados = roles_a_buscar(rol_elegido)
                    filas_contactos = []
                    with st.status("Verificando correos y buscando contactos...", expanded=True) as status:
                        for _, fila in grupo_a.iterrows():
                            correo = fila["Correo"]
                            status.update(label=f"Grupo A: verificando {correo}...")
                            try:
                                # Falla propia (no todo el try): un error transitorio de
                                # Hunter acá no debe cortar el resto de la cadena (Combined
                                # Enrichment, fallback por rol, otros correos del dominio),
                                # que no dependen de que la verificación haya funcionado.
                                try:
                                    verificacion = hunter_verificar_email(correo, HUNTER_API_KEY)
                                except Exception as exc_verificacion:
                                    verificacion = {"estado": "error de verificación — reintentar", "score": None}
                                    st.write(f"⚠ {correo} — no se pudo verificar con Hunter: {exc_verificacion}")
                                persona = None
                                if verificacion["estado"] not in ("invalid", "disposable"):
                                    try:
                                        persona = hunter_enriquecimiento_combinado(correo, HUNTER_API_KEY)
                                    except Exception as exc_combinado:
                                        st.write(f"⚠ {correo} — Combined Enrichment falló, sigo sin ese dato: {exc_combinado}")
                                dominio = dominio_de_empresa(correo, fila["Sitio web"])
                                score_final, confianza_final = calcular_score_correo(
                                    verificacion["score"], dominio, fila["Razón social"], SERPAPI_KEY
                                )

                                # Sin persona vía Hunter (típico en correos institucionales
                                # tipo ventas@/info@): fallback de búsqueda por rol. Se salta
                                # si el correo ya es claramente un buzón general (ej.
                                # archivogeneral@) — buscar una persona ahí siempre vuelve
                                # vacío. El correo del DENUE sigue siendo el contacto principal
                                # de la empresa — un correo alternativo que encuentre el
                                # fallback se agrega como fila aparte, no lo reemplaza.
                                correo_general = es_correo_general(correo)
                                contactos_fallback = []
                                contacto_fallback = None
                                if not persona and dominio and not correo_general:
                                    encontrados = []
                                    for terminos_rol in roles_seleccionados.values():
                                        resultado_rol = buscar_contacto_por_rol(
                                            fila["Razón social"], terminos_rol, SERPAPI_KEY, ANTHROPIC_API_KEY
                                        )
                                        if resultado_rol.nombre:
                                            encontrados.append(resultado_rol)
                                    contactos_fallback = _dedup_contactos(encontrados)
                                    contacto_fallback = contactos_fallback[0] if contactos_fallback else None

                                if persona:
                                    nombre_contacto, cargo_contacto, linkedin_contacto = (
                                        persona["nombre"], persona["cargo"], persona["linkedin"]
                                    )
                                    fuente_contacto = "DENUE + Hunter"
                                elif contacto_fallback:
                                    nombre_contacto, cargo_contacto, linkedin_contacto = (
                                        contacto_fallback.nombre, contacto_fallback.cargo, contacto_fallback.linkedin_url
                                    )
                                    fuente_contacto = "DENUE + Hunter + búsqueda web"
                                elif correo_general:
                                    nombre_contacto = cargo_contacto = linkedin_contacto = None
                                    fuente_contacto = "Correo general/institucional — sin contacto personal"
                                else:
                                    nombre_contacto = cargo_contacto = linkedin_contacto = None
                                    fuente_contacto = "DENUE + Hunter"

                                filas_contactos.append(fila_contacto(
                                    fila["Razón social"], nombre_contacto, correo, fila["Teléfono"],
                                    cargo_contacto, linkedin_contacto, es_principal=True,
                                    estado_correo=verificacion["estado"], score_correo=score_final,
                                    confianza_correo=confianza_final, fuente=fuente_contacto,
                                    cuenta_item_id=fila["Cuenta_item_id"],
                                    sector_empresa=fila["Actividad económica"],
                                    personal_estimado_empresa=fila["Personal estimado"],
                                    tamano_empresa=fila["Banda de tamaño"],
                                    sitio_web_empresa=fila["Sitio web"],
                                    correo_empresa=fila["Correo"],
                                ))

                                for contacto_alt in contactos_fallback:
                                    hallazgo_alt = hunter_buscar_email(dominio, contacto_alt.nombre, HUNTER_API_KEY)
                                    if hallazgo_alt and hallazgo_alt["email"] != correo:
                                        filas_contactos.append(fila_contacto(
                                            fila["Razón social"], contacto_alt.nombre, hallazgo_alt["email"],
                                            fila["Teléfono"], contacto_alt.cargo, contacto_alt.linkedin_url,
                                            es_principal=False, score_correo=hallazgo_alt["score"],
                                            fuente="Búsqueda por rol",
                                            sources="; ".join(hallazgo_alt["sources"]) if hallazgo_alt["sources"] else None,
                                            cuenta_item_id=fila["Cuenta_item_id"],
                                            sector_empresa=fila["Actividad económica"],
                                            personal_estimado_empresa=fila["Personal estimado"],
                                            tamano_empresa=fila["Banda de tamaño"],
                                            sitio_web_empresa=fila["Sitio web"],
                                            correo_empresa=fila["Correo"],
                                        ))

                                for otro in hunter_correos_del_dominio(dominio, HUNTER_API_KEY):
                                    filas_contactos.append(fila_contacto(
                                        fila["Razón social"], otro["nombre"], otro["correo"], fila["Teléfono"],
                                        otro["cargo"], otro["linkedin"], es_principal=False,
                                        score_correo=otro["confianza"], fuente="Hunter domain search",
                                        cuenta_item_id=fila["Cuenta_item_id"],
                                        sector_empresa=fila["Actividad económica"],
                                        personal_estimado_empresa=fila["Personal estimado"],
                                        tamano_empresa=fila["Banda de tamaño"],
                                        sitio_web_empresa=fila["Sitio web"],
                                        correo_empresa=fila["Correo"],
                                    ))

                                if correo_general:
                                    detalle = " — correo general/institucional, sin contacto personal"
                                elif nombre_contacto:
                                    detalle = f" — {nombre_contacto}"
                                else:
                                    detalle = " — sin persona identificada"
                                st.write(f"✓ {correo} — {verificacion['estado']} (score {score_final}, {confianza_final}){detalle}")
                            except Exception as exc:
                                st.write(f"✗ {correo} — error: {exc}")

                        for _, fila in grupo_b.iterrows():
                            razon = fila["Razón social"]
                            status.update(label=f"Grupo B: buscando {razon}...")
                            try:
                                dominio = extraer_dominio(fila["Sitio web"])

                                encontrados = []
                                for terminos_rol in roles_seleccionados.values():
                                    resultado_rol = buscar_contacto_por_rol(
                                        razon, terminos_rol, SERPAPI_KEY, ANTHROPIC_API_KEY
                                    )
                                    if resultado_rol.nombre:
                                        encontrados.append(resultado_rol)
                                contactos_b = _dedup_contactos(encontrados)

                                # Se resuelve el correo de cada candidato encontrado (no solo
                                # del primero) y se marca "principal" al de mejor score
                                # verificado — si ninguno tiene correo verificable, el primero.
                                candidatos = []
                                for contacto in contactos_b:
                                    correo_adivinado = None
                                    estado_correo = "sin dominio conocido para buscar" if not dominio else "no se pudo estimar un correo"
                                    score_final = None
                                    confianza_final = None
                                    fuentes_publicas = None
                                    if dominio:
                                        hallazgo = hunter_buscar_email(dominio, contacto.nombre, HUNTER_API_KEY)
                                        if hallazgo:
                                            verificacion = hunter_verificar_email(
                                                hallazgo["email"], HUNTER_API_KEY
                                            )
                                            correo_adivinado = hallazgo["email"]
                                            estado_correo = verificacion["estado"]
                                            score_final, confianza_final = calcular_score_correo(
                                                verificacion["score"], dominio, razon, SERPAPI_KEY
                                            )
                                            if hallazgo["sources"]:
                                                fuentes_publicas = "; ".join(hallazgo["sources"])
                                    candidatos.append(
                                        (contacto, correo_adivinado, estado_correo, score_final, confianza_final, fuentes_publicas)
                                    )

                                if candidatos:
                                    indice_principal = max(
                                        range(len(candidatos)),
                                        key=lambda i: candidatos[i][3] if candidatos[i][3] is not None else -1,
                                    )
                                    for i, (contacto, correo_adivinado, estado_correo, score_final, confianza_final, fuentes_publicas) in enumerate(candidatos):
                                        filas_contactos.append(fila_contacto(
                                            razon, contacto.nombre, correo_adivinado, fila["Teléfono"],
                                            contacto.cargo, contacto.linkedin_url, es_principal=(i == indice_principal),
                                            estado_correo=estado_correo, score_correo=score_final,
                                            confianza_correo=confianza_final, fuente="Búsqueda web + Hunter",
                                            sources=fuentes_publicas,
                                            cuenta_item_id=fila["Cuenta_item_id"],
                                            sector_empresa=fila["Actividad económica"],
                                            personal_estimado_empresa=fila["Personal estimado"],
                                            tamano_empresa=fila["Banda de tamaño"],
                                            sitio_web_empresa=fila["Sitio web"],
                                            correo_empresa=fila["Correo"],
                                        ))
                                    st.write(f"✓ {razon} — " + ", ".join(c.nombre for c, *_ in candidatos))
                                else:
                                    st.write(f"✗ {razon} — sin contacto encontrado")

                                if dominio:
                                    for otro in hunter_correos_del_dominio(dominio, HUNTER_API_KEY):
                                        filas_contactos.append(fila_contacto(
                                            razon, otro["nombre"], otro["correo"], fila["Teléfono"],
                                            otro["cargo"], otro["linkedin"], es_principal=False,
                                            score_correo=otro["confianza"], fuente="Hunter domain search",
                                            cuenta_item_id=fila["Cuenta_item_id"],
                                            sector_empresa=fila["Actividad económica"],
                                            personal_estimado_empresa=fila["Personal estimado"],
                                            tamano_empresa=fila["Banda de tamaño"],
                                            sitio_web_empresa=fila["Sitio web"],
                                            correo_empresa=fila["Correo"],
                                        ))
                            except Exception as exc:
                                st.write(f"✗ {razon} — error: {exc}")
                        status.update(label="Verificación y búsqueda completas", state="complete")
                    df_nuevo = pd.DataFrame(
                        filas_contactos, columns=COLUMNAS_CONTACTO_MONDAY + COLUMNAS_CONTACTO_INTERNAS
                    )
                    for columna_gestion in COLUMNAS_CONTACTO_GESTION:
                        df_nuevo[columna_gestion] = False
                    st.session_state["df_contactos"] = df_nuevo

                if "df_contactos" in st.session_state and not st.session_state["df_contactos"].empty:
                    df_contactos_vista = st.session_state["df_contactos"][
                        COLUMNAS_CONTACTO_MONDAY + COLUMNAS_CONTACTO_INTERNAS
                    ]
                    st.markdown(f"**Contactos encontrados ({len(df_contactos_vista)})**")
                    st.caption(
                        "Una fila por candidato de contacto, todos ligados a la misma 'Cuenta "
                        "asociada' — no solo el principal. 'Es principal' marca el más fuerte de "
                        "cada empresa; el resto son alternativas para respaldo. Columnas hasta "
                        "'Fecha de inicio' calzan con el board de Contacto en Monday; las que "
                        "siguen son contexto propio. La gestión de contacto y exportación a "
                        "Monday está en la pestaña 'Monday'."
                    )
                    st.dataframe(df_contactos_vista, hide_index=True)
                    st.download_button(
                        "Descargar contactos (CSV)",
                        data=df_contactos_vista.to_csv(index=False).encode("utf-8-sig"),
                        file_name="denue_contactos.csv",
                        mime="text/csv",
                        icon=":material/download:",
                    )

with tab_monday:
    st.subheader("Gestión y exportación a Monday")

    if "_monday_aviso" in st.session_state:
        _tipo_aviso, _mensaje_aviso = st.session_state.pop("_monday_aviso")
        getattr(st, _tipo_aviso)(_mensaje_aviso)

    if "df_contactos" not in st.session_state or st.session_state["df_contactos"].empty:
        st.info("Todavía no hay contactos — corré \"Verificar y buscar contactos\" en la pestaña Enriquecimiento.")
    elif not MONDAY_API_KEY:
        st.warning("Falta MONDAY_API_KEY en el .env para gestionar y exportar contactos.")
    else:
        st.caption(
            "Marcá 'Contactado' cuando ya hablaste con la persona, o 'No existe / "
            "desvinculado' si el contacto no sirve. 'Exportar a Monday' solo se habilita "
            "para contactos marcados como Contactado, y pide confirmación antes de crear "
            "el item en Monday."
        )
        usuarios_monday = monday_listar_usuarios()
        df_actual = st.session_state["df_contactos"]

        pendientes = df_actual[~df_actual["Exportado a Monday"] & ~df_actual["No existe / desvinculado"]]
        exportados = df_actual[df_actual["Exportado a Monday"]]
        no_existentes = df_actual[df_actual["No existe / desvinculado"] & ~df_actual["Exportado a Monday"]]

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Panel general", len(pendientes), border=True)
        col_m2.metric("Exportados a Monday", len(exportados), border=True)
        col_m3.metric("No existe / desvinculado", len(no_existentes), border=True)

        vista = st.segmented_control(
            "Categoría",
            options=["Panel general", "Exportados a Monday", "No existe / desvinculado"],
            default="Panel general",
            key="vista_monday",
            label_visibility="collapsed",
        )
        subset = {"Panel general": pendientes, "Exportados a Monday": exportados}.get(vista, no_existentes)

        st.divider()
        if subset.empty:
            st.caption("No hay contactos en esta categoría.")
        else:
            for idx, fila in subset.iterrows():
                _renderizar_tarjeta_contacto(idx, fila, usuarios_monday)
