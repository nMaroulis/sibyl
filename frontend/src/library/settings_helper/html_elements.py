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
                margin: 30px auto;
                box-shadow: 0 10px 20px rgba(0, 0, 0, 0.6);
                transition: transform 1.5s ease;
            }
            
            .settings-card-Active {
                box-shadow: 0 10px 20px rgba(11, 66, 6, 0.6); 
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
            
            .settings-card-Active button{
                color: white;
                background-color: #81c784;
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
            
            .settings-card-illustration-K img {
                box-shadow: 0 10px 15px rgba(138,43,226, 0.5); /* Added shadow for 3D effect */
            }
            
            .settings-card-illustration-C img {
                box-shadow: 0 10px 15px rgba(30,144,255, 0.5); /* Added shadow for 3D effect */
            }
            
            .settings-card-illustration-O img {
                box-shadow: 0 10px 15px rgba(95,158,160, 0.5); /* Added shadow for 3D effect */
            }
            
        </style>
    """)
    return


def status_card_header(title=""):
    html(f"""        
        <div class="status_header">
            <div class="status_line"></div>
            <div class="status_title">{title}</div>
            <div class="status_line"></div>
        </div>
    """)
    return


def status_card(name, logo, status='Active'):

    html(f"""
        <div class="settings-card settings-card-{status}">
            <div class="settings-card-illustration settings-card-illustration-{name[0]}">
                <img src="{logo}" width="120px" alt=""/>
            </div>
            <h3>{name}</h3>
            <button>{status}</button>
        </div>
    """)

# < div class ="settings-card settings-card-active" >
# < div class ="settings-card-illustration" >
# < img src = "https://www.logo.wine/a/logo/Binance/Binance-Vertical2-Dark-Background-Logo.wine.svg" width = "120px" /> </div >
# < h3 > Binance
# Testnet
# API < / h3 >
# < button > Active < / button >
# < / div >