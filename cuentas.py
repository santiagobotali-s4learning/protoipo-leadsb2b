"""
Integración con el board de Cuentas en Monday.com: clasificación de
empresas contra las cuentas ya cargadas, armado de perfil desde una cuenta
existente, y creación de cuentas nuevas. Ver structuraCuentas.md para el
esquema del board y docs/superpowers/specs/2026-09-09-tablero-cuentas-design.md
para las reglas de negocio.
"""


def clasificar_cuentas(df_empresas, cuentas_reales):
    """Clasifica df_empresas (con columna 'Razon_social') contra
    cuentas_reales — dict {nombre_normalizado: {item_id, tiene_convenio,
    tiene_contacto_exitoso, ...}}, ver monday_listar_cuentas_reales().
    Devuelve (df_nueva, df_existe_necesita_contacto, df_existe_gestionada),
    cada una con las columnas originales de df_empresas más 'Cuenta_item_id'
    (None si la cuenta es nueva). 'Gestionada' = tiene convenio o ya tiene
    un contacto con gestión exitosa (ver ESTADOS_CONTACTO_EXITOSO)."""
    nombres_normalizados = df_empresas["Razon_social"].astype(str).str.strip().str.lower()
    item_ids, gestionadas = [], []
    for nombre in nombres_normalizados:
        cuenta = cuentas_reales.get(nombre)
        if cuenta is None:
            item_ids.append(None)
            gestionadas.append(False)
        else:
            item_ids.append(cuenta["item_id"])
            gestionadas.append(cuenta["tiene_convenio"] or cuenta["tiene_contacto_exitoso"])

    df = df_empresas.copy()
    df["Cuenta_item_id"] = item_ids
    df["_gestionada"] = gestionadas

    df_nueva = df[df["Cuenta_item_id"].isna()].drop(columns="_gestionada")
    df_existe = df[df["Cuenta_item_id"].notna()]
    df_existe_necesita_contacto = df_existe[~df_existe["_gestionada"]].drop(columns="_gestionada")
    df_existe_gestionada = df_existe[df_existe["_gestionada"]].drop(columns="_gestionada")
    return df_nueva, df_existe_necesita_contacto, df_existe_gestionada
