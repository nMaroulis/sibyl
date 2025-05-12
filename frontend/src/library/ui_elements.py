from streamlit import set_page_config, html, cache_resource, logo, markdown, button, fragment
from PIL import Image


def fix_page_layout(page_name: str, padding_top: str = '2.1rem'):

    # im = Image.open("frontend/static/favicon/favicon-32x32.png")
    set_page_config(
        page_title=page_name,
        page_icon="frontend/static/favicon/favicon.ico",
        layout="wide",
    )
    logo("assets/logo_transparent.png", icon_image="assets/logo_brand.png",)
    html("""
            <style>
                   .block-container {
                        padding-top: """ + padding_top + """;
                    }
            </style>
            """)
    # FOOTER
    # html("""<style>
    # footer { visibility: hidden;}
    # footer:after {
    # content: 'developed by Nikolaos Maroulis';
    # visibility: visible;
    # position: relative;
    # top:50px;
    # right: 8em;
    # } </style>""")

    return 0

def set_page_title(page_name: str):
    html(f"""
        <h2 style="
            text-align: left; 
            margin-top: 1em; 
            padding: 0; 
            font-size: 1.6rem; 
            font-weight: 700; 
            color: #333;  /* Deep gray for a refined look */
            border-left: 5px solid #e07a5f; /* Soft orange accent */
            padding-left: 12px; /* Spacing for the border effect */
        ">
            {page_name}
        </h2>
    """)


col_style1 = """
    <style>
    [data-testid="stColumn"] {
        # background-color: #f9f9f9;
        box-shadow: 2px 2px 2px 2px rgba(0, 0, 0, 0.05);
        border-radius: 10px;
        padding: 22px;
        font-family: "serif";
    }
        [data-testid="stColumn"]:hover {
            background-color: #FDFDFD;
    }
    </style>
"""

col_style2 = """
    <style>
    [data-testid="stColumn"] {
        # background-color: #f9f9f9;
        box-shadow: 4px 4px 4px 4px rgba(0, 0, 0, 0.1);
        border-radius: 10px;
        padding: 22px;
        font-family: "serif";
    }
    [data-testid="stColumn"]:hover {
            background-color: #FDFDFD;
            transform: translateY(-1px); /* Added hover effect */
            filter: brightness(0.995);
            transition: transform 0.2s ease;
    }
    </style>
"""

col_style3 = """
<style>
[data-testid="stColumn"] {
    background-color: #fDfDfD;
    box-shadow: 6px 6px 6px rgba(0, 0, 0, 0.3);
    border-radius: 15px;
    padding: 22px;
    font-family: "serif";
}

[data-testid="stColumn"]:hover {
        transform: translateY(-5px); /* Added hover effect */
        filter: brightness(1.05);
        ::before{
          filter: brightness(.5);
          top: -100%;
          left: 200%;
        }
        transition: transform 0.9s ease;
}
</style>
"""


col_style4 = """
<style>
[data-testid="stColumn"] {
    background-color: #f9f9f9;
    box-shadow: 10px 10px 23px rgba(0, 0, 0, 0.4);
    border-radius: 15px;
    padding: 22px;
    font-family: "serif";
}

[data-testid="stColumn"]:hover {
        transform: translateY(-5px); /* Added hover effect */
        filter: brightness(1.05);
        ::before{
          filter: brightness(.5);
          top: -100%;
          left: 200%;
        }
        transition: transform 0.9s ease;
}
</style>
"""


container_style1 = """
    <style>
    [data-testid="stVerticalBlockBorderWrapper"] {
        # background-color: #f9f9f9;
        box-shadow: 4px 4px 4px 4px rgba(0, 0, 0, 0.1);
        border-radius: 10px;
        padding: 22px;
        font-family: "serif";
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
            background-color: #FDFDFD;
            transform: translateY(-1px); /* Added hover effect */
            filter: brightness(0.995);
            transition: transform 0.2s ease;
    }
    </style>
"""
