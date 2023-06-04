from streamlit import set_page_config, markdown, cache_resource
from PIL import Image


def fix_page_layout(page_name='Sibyl'):

    im = Image.open("/Users/nik/PycharmProjects/sibyl/frontend/static/favicon/favicon.ico")
    set_page_config(
        page_title=page_name,
        page_icon=im,
        layout="wide",
    )

    markdown("""
            <style>
                   .block-container {
                        padding-top: 1rem;
                    }
            </style>
            """, unsafe_allow_html=True)
    # padding - bottom: 0rem;
    # padding - left: 5rem;
    # padding - right: 5rem;

    markdown("""
    <style>
    footer { visibility: hidden;}
    footer:after {
    content: 'developed by Nikolaos Maroulis';
    visibility: visible;
    position: relative;
    top:5px;
    right: 8em;
    }
    </style>""", unsafe_allow_html=True)

    return 0
