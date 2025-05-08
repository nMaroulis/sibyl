from streamlit import set_page_config, html, cache_resource, logo, markdown
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
    # CUSTOM FONT
    # html("""
    #     <style>
    #     @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600&family=Inter:wght@300;400;600&display=swap');
    #
    #     html, body, h1, h2, h3, h4, h5, p {
    #         font-family: 'Poppins', 'Inter', sans-serif;
    #     }
    #     </style>
    # """)
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


def llm_advisor_button():
    markdown("""
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
        <style>
        .floating-chat {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 64px;
            height: 64px;
            background: linear-gradient(135deg, #8e44ad, #6c5ce7, #a29bfe);
            color: white;
            border: none;
            border-radius: 50%;
            box-shadow: 0 10px 25px rgba(142, 68, 173, 0.4);
            font-size: 28px;
            cursor: pointer;
            z-index: 1000;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: floatUpDown 3s ease-in-out infinite;
        }

        .floating-chat:hover {
            transform: scale(1.1) rotate(5deg);
            background: linear-gradient(135deg, #a29bfe, #6c5ce7, #8e44ad);
            box-shadow: 0 12px 28px rgba(108, 92, 231, 0.5);
        }

        @keyframes floatUpDown {
            0% { transform: translateY(0); }
            50% { transform: translateY(-6px); }
            100% { transform: translateY(0); }
        }
        </style>

        <button class="floating-chat" onclick="document.dispatchEvent(new CustomEvent('toggleAssistant'))">
            <i class="fas fa-comment-dots"></i>
        </button>

        <script>
        document.addEventListener('toggleAssistant', function () {
            window.parent.postMessage({ type: "streamlit:toggleAssistant" }, "*");
        });
        </script>
    """, unsafe_allow_html=True)
