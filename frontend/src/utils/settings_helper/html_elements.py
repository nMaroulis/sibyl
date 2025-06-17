from streamlit import html


def status_card_style():
    html("""
        <style>
            .settings-card {
                background-color: #F9F9F9;
                border-radius: 30px;
                text-align: center;
                padding: 10px;
                max-width: 180px;
                min-width: 173px;
                margin: 30px 20px;
                box-shadow: 0 10px 20px rgba(0, 0, 0, 0.6);
                transition: transform 1.5s ease;
            }
            
            .settings-card-Act {
                box-shadow: 0 10px 20px rgba(11, 66, 6, 0.6); 
                transition: transform 0.6s ease;
            }
            
            .settings-card-Inv {
                box-shadow: 0 10px 20px rgba(205,92,92, 0.6); 
                transition: transform 0.6s ease;
            }
            
            .settings-card:hover {
                transform: translateY(-5px); /* Added hover effect */
                filter: brightness(1.3);
                ::before{
                  filter: brightness(.5);
                  top: -100%;
                  left: 200%;
                }
            }
            
            .settings-card-illustration {
                margin: 8px;
            }
            
            .settings-card-illustration img {
                width: 100px;
                height: 100px;
                border-radius: 100%;
                overflow: hidden;
                margin: 0 auto;
                box-shadow: 0 10px 15px rgba(247, 228, 63, 0.5); /* Added shadow for 3D effect */
            }

            /*
            .settings-card-illustration img::before{
                position: fixed;
                content: "";
                box-shadow: 0 0 100px 40px #ffffff08;
                top: -10%;
                left: -100%;
                transform: rotate(-45deg);
                height: 60rem;
                transition: .7s all;
              }
            */
            
            .settings-card h3 {
                font-size: 1.0rem;
                line-height: 1.2rem;
                color: #555; /* Changed color for better visibility */
                font-weight: bold;
                margin: 5px 0;
            }
            
            .settings-card button {
                font-size: 0.8rem;
                font-weight: bold;
                padding: 5px 20px;
                border-radius: 25px;
                color: white;
                border: 0;
                margin: 5px 0;
                outline: none;
                background-color: #808080;
                # box-shadow: 0 4px 4px rgba(90, 145, 92, 0.4); /* Added shadow for 3D effect */
                transition: ease all 0.3s;
                cursor: pointer;
            }
            .settings-card button:hover {
                transform: translateY(-3px); /* Added hover effect */
                box-shadow: 0 15px 25px rgba(0, 0, 0, 0.2); /* Added shadow for hover effect */
            }
            .settings-card button:active {
                transform: scale(0.9);
            }
            
            .settings-card-Act button{
                color: white;
                background-color: #81c784;
            }

            .settings-card-Inv button{
                color: white;
                background-color: #DC143C;
            }
            
            .settings-card-Ina button{
                color: white;
                background-color: #DC143C;
            }
            
            .status_header {
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 4px 0;
            }
            .status_line {
                flex-grow: 1;
                height: 1px;
                background-color: #ddd; /* Color of the line */
            }
            .status_title {
                padding: 0 20px;
                font-size: 21px;
                color: #666;
            }
            
            .settings-card-illustration-Kr img {
                box-shadow: 0 10px 15px rgba(138,43,226, 0.5); /* Added shadow for 3D effect */
            }
            
            .settings-card-illustration-Co img {
                box-shadow: 0 10px 15px rgba(30,144,255, 0.5); /* Added shadow for 3D effect */
            }
            
            .settings-card-illustration-Ba img {
                box-shadow: 0 10px 15px rgba(30,144,255, 0.5); /* Added shadow for 3D effect */
            }
            
            .settings-card-illustration-Op img {
                box-shadow: 0 10px 15px rgba(95,158,160, 0.5); /* Added shadow for 3D effect */
            }
            
            .settings-card-illustration-Ge img {
                box-shadow: 0 10px 15px rgba(30,144,255, 0.5); /* Added shadow for 3D effect */
            }
            
            .settings-card-illustration-Mo img {
                box-shadow: 0 10px 15px rgba(0,0,0, 0.5); /* Added shadow for 3D effect */
            }
            
            .settings-card-illustration-Lo img {
                box-shadow: 0 10px 15px rgba(0,0,0, 0.5); /* Added shadow for 3D effect */
            }
            
            .settings-card-illustration-An img {
                box-shadow: 0 10px 15px rgba(227,199,161, 0.5);
            }

        </style>
    """)
    return


def status_card_header(title: str):
    html(f"""        
        <div class="status_header">
            <div class="status_line"></div>
            <div class="status_title">{title}</div>
            <div class="status_line"></div>
        </div>
    """)
    return


def status_card(name: str, logo: str, status: str = 'Active') -> str | None:

    html_txt = f"""
            <div class="settings-card settings-card-{status[0:3]}" style="display:inline-block;">
                <div class="settings-card-illustration settings-card-illustration-{name[0:2]}">
                    <img src="{logo}" width="120px" alt=""/>
                </div>
                <h3>{name}</h3>
                <button>{status}</button>
            </div>
        """
    return html_txt


def compact_card_style():
    html("""
        <style>
            .mini-card {
                background-color: #F9F9F9;
                border-radius: 15px;
                text-align: center;
                padding: 4px;
                max-width: 140px;
                min-width: 130px;
                margin: 15px 10px;
                box-shadow: 0 5px 10px rgba(0, 0, 0, 0.4);
                transition: transform 0.8s ease;
            }

            .mini-card-Active {
                box-shadow: 0 5px 10px rgba(11, 66, 6, 0.5);
            }

            .mini-card-Inactive {
                box-shadow: 0 5px 10px rgba(205,92,92, 0.5);
            }

            .mini-card:hover {
                transform: translateY(-3px);
                filter: brightness(1.2);
            }

            .mini-card-icon {
                margin: 5px;
            }

            .mini-card-icon img {
                width: 70px;
                height: 70px;
                border-radius: 50%;
                box-shadow: 0 5px 8px rgba(247, 228, 63, 0.4);
            }
            
            .mini-card-shadow-Kr img {
                box-shadow: 0 10px 15px rgba(138,43,226, 0.5); /* Added shadow for 3D effect */
            }
            
            .mini-card-shadow-Co img {
                box-shadow: 0 10px 15px rgba(30,144,255, 0.5); /* Added shadow for 3D effect */
            }
            
            .mini-card-shadow-Ba img {
                box-shadow: 0 10px 15px rgba(30,144,255, 0.5); /* Added shadow for 3D effect */
            }
            
            .mini-card-shadow-Op img {
                box-shadow: 0 10px 15px rgba(95,158,160, 0.5); /* Added shadow for 3D effect */
            }
            
            .mini-card-shadow-Ge img {
                box-shadow: 0 10px 15px rgba(30,144,255, 0.5); /* Added shadow for 3D effect */
            }

            
            .mini-card h4 {
                font-size: 0.7rem;
                color: #444;
                margin: 4px 0;
            }

            .mini-card button {
                font-size: 0.6rem;
                font-weight: bold;
                padding: 4px 15px;
                border-radius: 15px;
                color: white;
                border: none;
                margin: 4px 0;
                background-color: #808080;
                transition: all 0.3s ease;
                cursor: pointer;
            }
            .mini-card button:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 15px rgba(0, 0, 0, 0.15);
            }
            .mini-card button:active {
                transform: scale(0.95);
            }

            .mini-card-Active button {
                background-color: #4CAF50;
            }

            .mini-card-Inactive button {
                background-color: #D9534F;
            }
        </style>
    """)
    return


def compact_card_header(title: str):
    html(f"""        
        <div class="mini-header">
            <hr class="mini-line"/>
            <div class="mini-title">{title}</div>
            <hr class="mini-line"/>
        </div>
    """)
    return


def compact_card(name: str, logo: str, status: str = 'Active') -> str | None:
    html_txt = f"""
            <div class="mini-card mini-card-{status}" style="display:inline-block;">
                <div class="mini-card-icon mini-card-shadow-{name[0:2]}">
                    <img src="{logo}" alt=""/>
                </div>
                <h4>{name}</h4>
                <button>{status}</button>
            </div>
        """
    return html_txt
