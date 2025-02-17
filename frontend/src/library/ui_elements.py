from streamlit import set_page_config, markdown, cache_resource, logo
from PIL import Image


def fix_page_layout(page_name: str = 'Sibyl'):

    im = Image.open("frontend/static/favicon/favicon.ico")
    set_page_config(
        page_title=page_name,
        page_icon=im,
        layout="wide",
    )
    logo("assets/logo_transparent.png", icon_image="assets/logo_brand.png",)
    markdown("""
            <style>
                   .block-container {
                        padding-top: 2.7rem;
                    }
            </style>
            """, unsafe_allow_html=True)
    # padding - bottom: 0rem;
    # padding - left: 5rem;
    # padding - right: 5rem;

    # markdown("""
    # <style>
    # footer { visibility: hidden;}
    # footer:after {
    # content: 'developed by Nikolaos Maroulis';
    # visibility: visible;
    # position: relative;
    # top:50px;
    # right: 8em;
    # }
    # </style>""", unsafe_allow_html=True)

    return 0


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
