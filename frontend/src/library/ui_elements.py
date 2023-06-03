from streamlit import markdown


def fix_padding_top_and_footer():
    markdown("""
            <style>
                   .block-container {
                        padding-top: 0rem;
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

    # markdown("""
    # <footer class="css-164nlkn egzxvld1">
    # "Developed by"
    # <a href="//github.com/nMaroulis/sibyl" target="_blank" class="css-1vbd788 egzxvld2">
    # Nikolaos Maroulis </a>
    # </footer>
    # """, unsafe_allow_html=True)

    return 0