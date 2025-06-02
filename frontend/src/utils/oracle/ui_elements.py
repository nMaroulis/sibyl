from streamlit import markdown, fragment, button


@fragment()
def oracle_button(module: str, enabled: bool = True, content: dict = None):

    button_style = """
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
        button[kind="tertiary"] {
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
            --hover-transform: scale(1) rotate(0deg);
            transform: var(--hover-transform) translateY(0);
        }
        
        button[kind="tertiary"]::before {
            content: "\\f7e4"; /* Unicode for fa-search */
            font-family: "Font Awesome 6 Free"; /* or 5 if you’re using FA 5 */
            font-weight: 900; /* 900 for solid icons, 400 for regular */
            font-size: 20px;
            display: inline-block;
        }

        @keyframes floatUpDown {
            0% { transform: var(--hover-transform) translateY(0); }
            50% { transform: var(--hover-transform) translateY(-4px); }
            100% { transform: var(--hover-transform) translateY(0); }
        }
    """

    if enabled:
        button_style += """
            button[kind="tertiary"]:hover {
                --hover-transform: scale(1.2) rotate(5deg);
                background: linear-gradient(135deg, #a29bfe, #6c5ce7, #8e44ad);
                box-shadow: 0 12px 28px rgba(108, 92, 231, 0.5);
            }
        """
    else:
        button_style += """
            button[kind="tertiary"]:hover {
                background: #ccc;
                color: #888;
                cursor: not-allowed;
                box-shadow: none;
                animation: none;
                transform: none;
            }
        """
    button_style += """</style>"""
    ##### DEPRECATED CODE - to be removed
    # <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    # <button class="floating-chat" onclick="document.dispatchEvent(new CustomEvent('toggleAssistant'))">
    #     <i class="fas fa-comment-dots"></i>
    # </button>
    # ....
    #     <script>
    #     document.addEventListener('toggleAssistant', function () {
    #         window.parent.postMessage({ type: "streamlit:toggleAssistant" }, "*");
    #     });
    #     </script>
    markdown(button_style, unsafe_allow_html=True)

    # button is now called from each module
    # if button("", type="tertiary", icon=":material/rocket_launch:"):
    #     dialog_map(module, content)

    if not enabled:
        button("", type="tertiary")
