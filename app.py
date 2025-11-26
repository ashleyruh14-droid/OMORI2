import streamlit as st
import datetime as dt
import os
import csv
import math
import streamlit.components.v1 as components

# ---------------------------------------------------
# CONFIG DE LA PAGE
# ---------------------------------------------------
st.set_page_config(
    page_title="Contrôle de poids OMORI 2",
    page_icon="🧪",
    layout="wide"
)

POSTE_FIXE = "OMORI 2"
ADMIN_PASSWORD = "Julia1954B"  # Mot de passe responsable

# 👉 CSS pour masquer la sidebar à l'impression
st.markdown(
    """
    <style>
    @media print {
        section[data-testid="stSidebar"] {
            display: none !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------
# TABLES DE RÉFÉRENCE
# ---------------------------------------------------

POIDS_MIN_OMORI2 = {
    50: 45.5,
    70: 65.5,
    85: 80.5,
    100: 95.5,
    120: 114.6,
    150: 143.3,
    180: 171.9,
    200: 191.0,
    225: 216.0,
    250: 241.0,
    500: 485.0,
    700: 685.0,
    800: 785.0,
    1000: 985.0,
}

# Valeurs de g (tirées du tableau de l'IQ-02, complétées) :contentReference[oaicite:3]{index=3}
G_VALUES = {
    2: 2.176,
    3: 1.089,
    4: 0.819,
    5: 0.686,
    6: 0.603,
    7: 0.544,
    8: 0.500,
    9: 0.466,
    10: 0.437,
    11: 0.414,
    12: 0.394,
    13: 0.376,
    14: 0.361,
    15: 0.347,
    16: 0.335,
    17: 0.324,
    18: 0.314,
    19: 0.305,
    20: 0.297,
    21: 0.289,
    22: 0.282,
    23: 0.275,
    24: 0.269,
    25: 0.264,
    26: 0.258,
    27: 0.253,
    28: 0.248,
    29: 0.244,
    30: 0.239,
    31: 0.235,
    32: 0.231,
    33: 0.228,
    34: 0.224,
    35: 0.221,
    36: 0.218,
    37: 0.215,
    38: 0.212,
    39: 0.209,
    40: 0.206,
    41: 0.204,
    42: 0.201,
    43: 0.199,
    44: 0.196,
    45: 0.194,
    46: 0.192,
    47: 0.190,
    48: 0.188,
    49: 0.186,
    50: 0.184,
    55: 0.175,
    60: 0.167,
    65: 0.161,
    70: 0.155,
    75: 0.149,
    80: 0.144,
}

# ---------------------------------------------------
# FONCTIONS UTILES
# ---------------------------------------------------

def is_admin() -> bool:
    """Retourne True si le mode responsable est activé."""
    if "is_admin_valid" not in st.session_state:
        st.session_state["is_admin_valid"] = False
    return st.session_state["is_admin_valid"]


def get_poids_min(poids_produit):
    """Retourne le poids minimum toléré pour OMORI 2."""
    if not poids_produit:
        return None
    p = int(round(poids_produit))
    return POIDS_MIN_OMORI2.get(p)


def zones_1er_controle(nb_pesees: int):
    """
    Zones du 1er contrôle (conforme aux tableaux IQ-02) :contentReference[oaicite:4]{index=4}
    Retourne (accept_max, refus_min).
    """
    if nb_pesees == 30:
        # Acceptation : 0 ; 2e contrôle : 1 ; Refus : >=2
        return 0, 2
    elif nb_pesees == 50:
        # Acceptation : <=1 ; 2e contrôle : 2 ; Refus : >=3
        return 1, 3
    elif nb_pesees == 80:
        # Acceptation : <=1 ; 2e contrôle : 2 ou 3 ; Refus : >=4
        return 1, 4
    # Sécurité pour d'autres valeurs (on raisonne "à la louche")
    if nb_pesees < 30:
        return 0, 2
    elif nb_pesees < 50:
        return 1, 3
    elif nb_pesees < 80:
        return 2, 4
    else:
        return 3, 5


def max_nc_total_2eme_controle(nb_pesees_par_controle: int) -> int:
    """
    Nombre total de NC autorisés après 2 contrôles (sur 60 / 100 / 160 pesées). :contentReference[oaicite:5]{index=5}
    nb_pesees_par_controle : nombre de pesées effectuées à CHAQUE contrôle (30, 50 ou 80).
    Retourne le max de NC tolérés au total (1er + 2e).
    """
    if nb_pesees_par_controle == 30:   # 60 au total
        return 1
    elif nb_pesees_par_controle == 50: # 100 au total
        return 2
    elif nb_pesees_par_controle == 80: # 160 au total
        return 3
    # Valeur par défaut prudente
    return max(1, nb_pesees_par_controle // 40)


def get_g_value(n: int):
    """Retourne g pour un effectif n, en prenant la dernière valeur connue si n n'est pas listé."""
    if n in G_VALUES:
        return G_VALUES[n]
    candidats = [k for k in G_VALUES.keys() if k <= n]
    if not candidats:
        return None
    return G_VALUES[max(candidats)]


def calc_stats_g(valeurs, poids_min):
    """
    Calcule moyenne, écart-type estimé et test g.
    Retourne (moyenne, s, g, seuil_stat, critere_ok)
    """
    n = len(valeurs)
    if n == 0:
        return None, None, None, None, True

    moyenne = sum(valeurs) / n

    if n > 1:
        variance = sum((v - moyenne) ** 2 for v in valeurs) / (n - 1)
        s = math.sqrt(variance)
    else:
        s = 0.0

    g = get_g_value(n)
    if g is None:
        return moyenne, s, None, None, True

    m = poids_min
    seuil_stat = m + g * s
    critere_ok = moyenne >= seuil_stat

    return moyenne, s, g, seuil_stat, critere_ok


def compute_lot(date_cond: dt.date, e_jour: int | None) -> str:
    """
    Calcule le n° de lot automatique :
    - Année codée sur 3 chiffres (année - 2000), ex : 2025 -> 025
    - Quantième sur 3 chiffres
    - Optionnellement 'E' + jour d'embossage (1 à 31) sur 2 chiffres
    => ex : 25/11/2025, E = 24 -> 025329E24
    """
    if not date_cond:
        return ""
    doy = date_cond.timetuple().tm_yday
    year_code = date_cond.year - 2000
    lot_base = f"{year_code:03d}{doy:03d}"
    if e_jour:
        lot = f"{lot_base}E{int(e_jour):02d}"
    else:
        lot = lot_base
    return lot


def write_log(
    operateur,
    verdict,
    produit,
    lot,
    date_fab,
    date_cond,
    e_jour,
    poids_produit,
    quantite_reelle,
    poids_min,
    nb_pesees,
    moyenne_1,
    nb_nc_1,
    moyenne_globale,
    nb_nc_total,
    valeurs_1,
    valeurs_2,
):
    """
    Enregistre un contrôle dans un fichier CSV d'historique pour OMORI 2.
    Si le fichier n'existe pas, il est recréé avec un en-tête propre.
    """

    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "historique_controles_omori2.csv")
    file_exists = os.path.isfile(csv_path)

    now = dt.datetime.now()
    date_enr = now.strftime("%Y-%m-%d")
    heure_enr = now.strftime("%H:%M:%S")

    details_p1 = "|".join(f"{v:.2f}" for v in valeurs_1) if valeurs_1 else ""
    details_p2 = "|".join(f"{v:.2f}" for v in valeurs_2) if valeurs_2 else ""

    try:
        with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")

            if not file_exists:
                writer.writerow([
                    "Date enregistrement",
                    "Heure enregistrement",
                    "Opérateur",
                    "Poste",
                    "Produit",
                    "Lot",
                    "E (jour)",
                    "Date fabrication",
                    "Date conditionnement",
                    "Poids produit (g)",
                    "Quantité produite réelle (uc)",
                    "Poids min toléré (g)",
                    "Nombre de pesées par contrôle",
                    "Moyenne 1er contrôle (g)",
                    "Nb NC 1er contrôle",
                    "Moyenne globale (1er + 2e) (g)",
                    "Nb NC total (1er + 2e)",
                    "Détail pesées 1er contrôle",
                    "Détail pesées 2e contrôle",
                    "Verdict final",
                ])

            writer.writerow([
                date_enr,
                heure_enr,
                operateur,
                POSTE_FIXE,
                produit,
                lot,
                e_jour if e_jour is not None else "",
                date_fab.strftime("%Y-%m-%d"),
                date_cond.strftime("%Y-%m-%d"),
                poids_produit,
                quantite_reelle,
                poids_min,
                nb_pesees,
                f"{moyenne_1:.2f}" if moyenne_1 is not None else "",
                nb_nc_1 if nb_nc_1 is not None else "",
                f"{moyenne_globale:.2f}" if moyenne_globale is not None else "",
                nb_nc_total if nb_nc_total is not None else "",
                details_p1,
                details_p2,
                verdict,
            ])
    except PermissionError:
        st.error(
            "❌ Impossible d'enregistrer l'historique.\n\n"
            "Le fichier d'historique (historique_controles_omori2.csv) est probablement ouvert.\n"
            "➡ Merci de **fermer le fichier**, puis relancer l'enregistrement."
        )


def reset_app():
    """Réinitialise complètement l'application."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def validate_general_fields(operateur, produit, date_fab, date_cond, e_jour, poids_produit, quantite_theo):
    """Vérifie que toutes les infos générales sont remplies, sinon affiche des erreurs."""
    ok = True
    if not operateur:
        st.error("Merci de remplir le **nom de l'opérateur** pour continuer.")
        ok = False
    if not produit:
        st.error("Merci de sélectionner un **produit** pour continuer.")
        ok = False
    if not date_fab:
        st.error("Merci de renseigner la **date de fabrication**.")
        ok = False
    if not date_cond:
        st.error("Merci de renseigner la **date de conditionnement**.")
        ok = False
    if not e_jour:
        st.error("Merci de renseigner **E (jour d'embossage)**.")
        ok = False
    if poids_produit <= 0:
        st.error("Merci de renseigner un **poids de produit** strictement supérieur à 0.")
        ok = False
    if quantite_theo <= 0:
        st.error("Merci de renseigner une **quantité théorique produite** strictement supérieure à 0.")
        ok = False
    return ok


# ---------------------------------------------------
# BARRE LATERALE – MODE RESPONSABLE
# ---------------------------------------------------

st.sidebar.header("Mode responsable")
admin_checkbox = st.sidebar.checkbox("Activer le mode responsable")
admin_code = st.sidebar.text_input("Code responsable", type="password")

if admin_checkbox and admin_code == ADMIN_PASSWORD:
    st.sidebar.success("Mode responsable activé.")
    st.session_state["is_admin_valid"] = True
elif admin_checkbox and admin_code:
    st.sidebar.error("Code responsable incorrect.")
    st.session_state["is_admin_valid"] = False
else:
    if not admin_checkbox:
        st.session_state["is_admin_valid"] = False

# ---------------------------------------------------
# LOGO + TITRE + BOUTON RESET
# ---------------------------------------------------

col_title, col_logo = st.columns([3, 1])

with col_title:
    st.title("Contrôle de poids 🧪 – Ligne OMORI 2")
    st.markdown(
        "Application de contrôle de poids avec intégration du contrôle statistique (valeur de g, risque 10 %)."
    )

with col_logo:
    try:
        st.image("logo+berni.png", width=120)
    except Exception:
        st.write("")

st.divider()

reset_col, info_col = st.columns([1, 3])
with reset_col:
    if st.button("🔄 Nouvelle pesée / réinitialiser"):
        reset_app()
with info_col:
    st.caption("Clique sur **Nouvelle pesée** pour repartir sur un lot complètement vierge.")

st.markdown("---")

# ---------------------------------------------------
# 1. INFOS GÉNÉRALES
# ---------------------------------------------------

st.header("Étape 1 : Informations générales")

col0, col1, col2, col3 = st.columns(4)

with col0:
    operateur = st.text_input("Nom de l'opérateur")

with col1:
    produit = st.selectbox(
        "Produit",
        [
            "",
            "Boeuf Mouton",
            "Boeuf Volaille",
            "Chorizo au jambon",
            "Chorizo espagnol Doux",
            "Chorizo espagnol ExtraFort",
            "Chorizo espagnol Fort",
            "Chorizo XXL",
            "Eco doux",
            "Eco fort",
            "Economy Doux",
            "Economy Fort",
            "Fumé Lorrain",
            "Lidl extra fort",
            "Lidl fort",
            "Lidl doux",
            "Netto doux",
            "Netto fort",
            "Olives",
            "Porc et boeuf fort",
            "PPD",
            "PPF",
            "Self",
            "Supérieur doux",
            "Supérieur extra fort",
            "Supérieur fort",
            "Taureau Doux",
            "Taureau Extra fort",
            "Taureau fort",
            "TOP doux",
            "TOP fort",
        ]
    )

with col2:
    # E = jour d'embossage (1 à 31)
    today = dt.date.today()
    default_e = today.day
    e_jour = st.selectbox(
        "E (jour d'embossage)",
        options=list(range(1, 32)),
        index=default_e - 1 if 1 <= default_e <= 31 else 0,
        help="Choisir le jour d'embossage (1 à 31)."
    )

with col3:
    # Date fabrication
    date_fab = st.date_input("Date de fabrication", value=dt.date.today())

col4, col5, col6 = st.columns(3)

with col4:
    # Date conditionnement = aujourd'hui par défaut, modifiable uniquement en admin
    if is_admin():
        date_cond = st.date_input("Date de conditionnement", value=dt.date.today())
    else:
        date_cond = st.date_input("Date de conditionnement", value=dt.date.today(), disabled=True)

with col5:
    poids_produit = st.number_input("Poids du produit (g)", min_value=0.0, step=0.1)

with col6:
    quantite_theo = st.number_input("Quantité théorique produite (uc)", min_value=0, step=1)

# ---------------------------------------------------
# NUMÉRO DE LOT (AUTO + MODIFIABLE EN ADMIN)
# ---------------------------------------------------

lot_auto = compute_lot(date_cond, e_jour)

if is_admin():
    lot_default = st.session_state.get("lot_force", lot_auto)
    lot_input = st.text_input(
        "Numéro de lot",
        value=lot_default,
        help="Le responsable peut modifier manuellement le numéro de lot."
    )
    st.session_state["lot_force"] = lot_input
    lot = lot_input
else:
    lot = lot_auto
    st.text_input(
        "Numéro de lot",
        value=lot,
        disabled=True,
        help="Numéro de lot généré automatiquement (année + quantième + E + jour embossage)."
    )

st.markdown("---")

# ---------------------------------------------------
# 2. POIDS MIN TOLÉRÉ
# ---------------------------------------------------

st.header("Étape 2 : Tolérance de poids")

poids_min = None
if poids_produit > 0:
    poids_min = get_poids_min(poids_produit)
    if poids_min is not None:
        st.success(
            f"Poids minimum toléré (Tu1) pour **{int(round(poids_produit))} g** "
            f"sur **{POSTE_FIXE}** : **{poids_min:.2f} g**"
        )
    else:
        st.error(
            "⚠️ Ce poids de produit n'est pas défini dans les tables codées.\n\n"
            "Ajoute-le dans le dictionnaire `POIDS_MIN_OMORI2` au début du fichier."
        )
else:
    st.info("Renseigne d'abord le **poids du produit** pour calculer le poids mini toléré.")

st.markdown("---")

# ---------------------------------------------------
# 3. NOMBRE DE PESÉES
# ---------------------------------------------------

st.header("Étape 3 : Nombre de pesées à effectuer")

nb_pesees = 0
if quantite_theo > 0:
    # Conforme au tableau IQ-02 : ≤100 -> toutes les unités ; 100–500 -> 30 ; 501–3200 -> 50 ; >3200 -> 80 :contentReference[oaicite:6]{index=6}
    if quantite_theo <= 100:
        nb_pesees = int(quantite_theo)
    elif quantite_theo <= 500:
        nb_pesees = 30
    elif quantite_theo <= 3200:
        nb_pesees = 50
    else:
        nb_pesees = 80

st.write(f"**Nombre de pesées à effectuer par contrôle :** {nb_pesees if nb_pesees > 0 else '-'}")

st.markdown("---")

# ---------------------------------------------------
# 4. 1er CONTRÔLE
# ---------------------------------------------------

st.header("Étape 4 : 1er contrôle de pesée")

moyenne_1 = None
nb_nc_1 = None

if nb_pesees == 0 or not poids_min:
    st.info(
        "Pour lancer le 1er contrôle, il faut :\n"
        "- un poids de produit défini dans les tables\n"
        "- une quantité théorique produite > 0\n"
        "- toutes les informations générales remplies"
    )
else:
    st.subheader("Saisie des pesées (1er contrôle)")

    valeurs_1 = []
    cols = st.columns(4)

    for i in range(nb_pesees):
        col = cols[i % 4]
        with col:
            v = st.number_input(
                f"Pesée {i+1}",
                key=f"p1_{i}",
                step=0.1,
                min_value=0.0
            )
            valeurs_1.append(v)

            if poids_min and v > 0 and v < poids_min:
                st.markdown(
                    "<div style='border:2px solid red; padding:2px; "
                    "border-radius:4px; color:red; font-size:12px;'>Non conforme</div>",
                    unsafe_allow_html=True,
                )

    if st.button("Analyser le 1er contrôle"):
        # Vérifier d'abord que toutes les infos générales sont remplies
        if not validate_general_fields(operateur, produit, date_fab, date_cond, e_jour, poids_produit, quantite_theo):
            st.stop()

        # Vérifier que toutes les pesées sont remplies
        if any(v <= 0 for v in valeurs_1):
            st.error("Merci de **remplir toutes les pesées du 1er contrôle** (aucune valeur ne doit être à 0).")
            st.stop()

        valeurs_valides = valeurs_1[:]  # toutes > 0

        moyenne_1, s1, g1, seuil_stat_1, critere_g_1 = calc_stats_g(valeurs_valides, poids_min)
        non_conformes_1 = [v for v in valeurs_valides if v < poids_min]
        nb_nc_1 = len(non_conformes_1)
        accept_max, refus_min = zones_1er_controle(len(valeurs_valides))

        st.write(f"**Moyenne 1er contrôle :** {moyenne_1:.2f} g")
        st.write(f"**Écart-type estimé (s) :** {s1:.3f} g" if s1 is not None else "Écart-type non calculé")
        st.write(
            f"**Nombre de pesées non conformes (TU1) :** {nb_nc_1} "
            f"/ {len(valeurs_valides)} (acceptation si ≤ {accept_max}, refus direct si ≥ {refus_min}) "
            f"(seuil poids {poids_min:.2f} g)"
        )

        if g1 is not None and seuil_stat_1 is not None:
            st.write(
                f"**Contrôle statistique (g)** : n = {len(valeurs_valides)}, g = {g1:.3f} → "
                f"moyenne = {moyenne_1:.2f} g, seuil requis = {seuil_stat_1:.2f} g "
                f"({'OK' if critere_g_1 else 'NON OK'})"
            )

        conforme_nc_accept = nb_nc_1 <= accept_max
        nc_refus_direct = nb_nc_1 >= refus_min
        conforme_g = critere_g_1

        # On garde les valeurs du 1er contrôle pour le 2e
        st.session_state["valeurs_1"] = valeurs_valides
        st.session_state["moyenne_1"] = moyenne_1
        st.session_state["nb_nc_1"] = nb_nc_1
        st.session_state["poids_min"] = poids_min
        st.session_state["nb_pesees"] = nb_pesees
        st.session_state["infos_generales"] = {
            "operateur": operateur,
            "produit": produit,
            "date_fab": date_fab,
            "date_cond": date_cond,
            "e_jour": e_jour,
            "poids_produit": poids_produit,
            "quantite_theo": quantite_theo,
            "lot": lot,
        }

        # Logique conforme au schéma IQ-02 :contentReference[oaicite:7]{index=7}
        if conforme_nc_accept and conforme_g:
            verdict = "Lot conforme au 1er contrôle"
            st.success(f"✅ {verdict}.")
            st.session_state["premier_controle_conforme"] = True
            st.session_state["premier_controle_effectue"] = True
            st.session_state["deuxieme_controle_autorise"] = False
            st.session_state["verdict_final"] = verdict

        elif nc_refus_direct:
            verdict = "Lot NON CONFORME au 1er contrôle - STOP"
            st.error("🛑 **Lot refusé au 1er contrôle (trop de TU1). Prévenez votre responsable / Service Qualité.**")
            st.session_state["premier_controle_conforme"] = False
            st.session_state["premier_controle_effectue"] = True
            st.session_state["deuxieme_controle_autorise"] = False
            st.session_state["verdict_final"] = verdict

        else:
            # Zone "faire un 2e contrôle" ou échec du g alors que NC OK
            st.warning("⚠️ Lot en zone intermédiaire → effectuer un **2ème contrôle**.")
            st.session_state["premier_controle_conforme"] = False
            st.session_state["premier_controle_effectue"] = True
            st.session_state["deuxieme_controle_autorise"] = True
            st.session_state["verdict_final"] = None

st.markdown("---")

# ---------------------------------------------------
# 5. 2ème CONTRÔLE
# ---------------------------------------------------

st.header("Étape 5 : 2ème contrôle (si nécessaire)")

valeurs_1_session = st.session_state.get("valeurs_1", [])
moyenne_1_session = st.session_state.get("moyenne_1", None)
nb_nc_1_session = st.session_state.get("nb_nc_1", None)

moyenne_globale = None
nb_nc_total = None
valeurs_2 = []

if (
    st.session_state.get("premier_controle_effectue")
    and not st.session_state.get("premier_controle_conforme")
    and st.session_state.get("deuxieme_controle_autorise", False)
):
    st.subheader("Saisie des pesées (2ème contrôle)")

    cols2 = st.columns(4)
    for i in range(st.session_state.get("nb_pesees", 0)):
        col = cols2[i % 4]
        with col:
            v2 = st.number_input(
                f"Pesée 2-{i+1}",
                key=f"p2_{i}",
                step=0.1,
                min_value=0.0
            )
            valeurs_2.append(v2)

            if poids_min and v2 > 0 and v2 < poids_min:
                st.markdown(
                    "<div style='border:2px solid red; padding:2px; "
                    "border-radius:4px; color:red; font-size:12px;'>Non conforme</div>",
                    unsafe_allow_html=True,
                )

    if st.button("Analyser le 2ème contrôle"):
        # Vérifier que toutes les pesées sont remplies
        if any(v <= 0 for v in valeurs_2):
            st.error("Merci de **remplir toutes les pesées du 2ème contrôle** (aucune valeur ne doit être à 0).")
            st.stop()

        valeurs_valides_2 = valeurs_2[:]
        non_conformes_2 = [v for v in valeurs_valides_2 if v < poids_min]
        nb_nc_2 = len(non_conformes_2)

        # Moyenne globale sur les 2 contrôles
        toutes_valeurs = list(valeurs_1_session) + list(valeurs_valides_2)
        moyenne_globale, s_tot, g_tot, seuil_stat_tot, critere_g_tot = calc_stats_g(
            toutes_valeurs, poids_min
        )

        nb_pesees_par_controle = st.session_state.get("nb_pesees", 0)
        total_pesees = len(toutes_valeurs)
        max_nc_autorise_total = max_nc_total_2eme_controle(nb_pesees_par_controle)

        nb_nc_total = (nb_nc_1_session or 0) + nb_nc_2

        st.write(f"**Moyenne globale (1er + 2ème contrôle) :** {moyenne_globale:.2f} g")
        st.write(f"**Écart-type global (s) :** {s_tot:.3f} g" if s_tot is not None else "Écart-type non calculé")
        st.write(
            f"**Nombre total de pesées :** {total_pesees} "
            f"(2 × {nb_pesees_par_controle})"
        )
        st.write(
            f"**Nombre total de pesées non conformes (TU1) sur 1er + 2e contrôle :** {nb_nc_total} "
            f"(acceptation si ≤ {max_nc_autorise_total})"
        )

        if g_tot is not None and seuil_stat_tot is not None:
            st.write(
                f"**Contrôle statistique global (g)** : n = {len(toutes_valeurs)}, g = {g_tot:.3f} → "
                f"moyenne globale = {moyenne_globale:.2f} g, seuil requis = {seuil_stat_tot:.2f} g "
                f"({'OK' if critere_g_tot else 'NON OK'})"
            )

        conforme_nc_2 = nb_nc_total <= max_nc_autorise_total
        conforme_g_2 = critere_g_tot

        if conforme_nc_2 and conforme_g_2:
            verdict = "Lot conforme après le 2ème contrôle"
            st.success(f"✅ {verdict}.")
            st.session_state["verdict_final"] = verdict
        else:
            verdict = "Lot NON CONFORME après le 2ème contrôle - STOP"
            st.error("🛑 **STOP, prévenez votre responsable et bloquez le produit !**")
            if not conforme_nc_2:
                st.warning("➜ Dépassement de la tolérance sur le **nombre total de pesées non conformes**.")
            if not conforme_g_2:
                st.warning("➜ Échec du **contrôle statistique global** (moyenne trop proche du mini).")

            st.session_state["verdict_final"] = verdict

        st.session_state["moyenne_globale"] = moyenne_globale
        st.session_state["nb_nc_total"] = nb_nc_total
        st.session_state["valeurs_2"] = valeurs_valides_2
else:
    st.info("Le 2ème contrôle n'est disponible que si le 1er contrôle est en zone intermédiaire (TU1).")

st.markdown("---")

# ---------------------------------------------------
# 6. BOUTON IMPRIMER + QUANTITÉ RÉELLE
# ---------------------------------------------------

if st.session_state.get("verdict_final"):
    st.markdown("### 🧾 Actions de fin de contrôle")

    infos = st.session_state.get("infos_generales", {})
    operateur_info = infos.get("operateur", operateur)
    produit_info = infos.get("produit", produit)
    date_fab_info = infos.get("date_fab", date_fab)
    date_cond_info = infos.get("date_cond", date_cond)
    e_jour_info = infos.get("e_jour", e_jour)
    poids_produit_info = infos.get("poids_produit", poids_produit)
    quantite_theo_info = infos.get("quantite_theo", quantite_theo)
    lot_info = infos.get("lot", lot)
    poids_min_info = st.session_state.get("poids_min", poids_min)
    nb_pesees_info = st.session_state.get("nb_pesees", nb_pesees)

    moyenne_1_finale = moyenne_1_session
    nb_nc_1_final = nb_nc_1_session
    moyenne_globale_finale = st.session_state.get("moyenne_globale", moyenne_1_session)

    # Nb NC total pour l'export : si pas de 2e contrôle, on prend nb_nc_1
    nb_nc_total_final = st.session_state.get("nb_nc_total", nb_nc_1_final)

    valeurs_1_finales = valeurs_1_session
    valeurs_2_finales = st.session_state.get("valeurs_2", [])

    st.write(f"**Verdict :** {st.session_state['verdict_final']}")

    # Quantité réelle obligatoire
    quantite_reelle = st.number_input(
        "Quantité réellement produite (uc)",
        min_value=0,
        step=1,
        help="Saisir la quantité réelle après tri des produits non conformes."
    )

    if st.button("💾 Enregistrer dans l'historique + préparer l'impression"):
        if quantite_reelle <= 0:
            st.error("Merci de saisir une **quantité réellement produite** strictement supérieure à 0.")
        else:
            write_log(
                operateur=operateur_info,
                verdict=st.session_state["verdict_final"],
                produit=produit_info,
                lot=lot_info,
                date_fab=date_fab_info,
                date_cond=date_cond_info,
                e_jour=e_jour_info,
                poids_produit=poids_produit_info,
                quantite_reelle=int(quantite_reelle),
                poids_min=poids_min_info,
                nb_pesees=nb_pesees_info,
                moyenne_1=moyenne_1_finale,
                nb_nc_1=nb_nc_1_final,
                moyenne_globale=moyenne_globale_finale,
                nb_nc_total=nb_nc_total_final,
                valeurs_1=valeurs_1_finales,
                valeurs_2=valeurs_2_finales,
            )
            st.success("✅ Contrôle enregistré dans l'historique.")
            st.session_state["trigger_print"] = True

# Impression (la suppression de la date/heure se fait dans les options du navigateur)
if st.session_state.get("trigger_print"):
    components.html(
        """
        <script>
        window.parent.print();
        </script>
        """,
        height=0,
    )
    st.session_state["trigger_print"] = False

