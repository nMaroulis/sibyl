import matplotlib.pyplot as plt
from matplotlib import cm, colors, colorbar


def risk_gauge(risk):
    colors = ['#fabd57', '#f6ee54', '#c1da64', '#72c66e','#4dab6d']  # Green to yellow-orange
    values = [1.5, 3.5, 5.5, 7.5, 9.5]  # Representing Excellent to Very Poor
    x_axis_vals = [0, 0.63 ,1.26, 1.89, 2.52]  # These values now spread evenly for 5 categories
    fig = plt.figure(figsize=(18, 18))
    ax = fig.add_subplot(projection="polar")
    ax.bar(x=x_axis_vals, width=0.63, height=0.5, bottom=2,
           linewidth=3, edgecolor="white", color=colors, align="edge")
    plt.annotate("Very High", xy=(0.17, 2.02), rotation=-75, color="white", fontweight="bold", fontsize=28)
    plt.annotate("High", xy=(0.96, 2.05), rotation=-42, color="white", fontweight="bold", fontsize=28)
    plt.annotate("Moderate", xy=(1.73, 2.2), rotation=0, color="white", fontweight="bold", fontsize=28)
    plt.annotate("Low", xy=(2.3, 2.2), rotation=42, color="white", fontweight="bold", fontsize=28)
    plt.annotate("Very Low", xy=(3,2.28), rotation=75, color="white", fontweight="bold", fontsize=28)
    for loc, val in zip(x_axis_vals, values):
        plt.annotate(f"{int(val)}", xy=(loc, 2.5), ha="center", color="white", fontweight="bold")

    tick_dict = {
        1: 3.1,
        2: 2.7,
        3: 2.38,
        4: 2.04,
        5: 1.74,
        6: 1.42,
        7: 1.12,
        8: 0.82,
        9: 0.42,
        10: 0
    }
    plt.annotate(str(risk), xytext=(0, 0), xy=(tick_dict[risk], 2.1),
                 arrowprops=dict(arrowstyle="wedge, tail_width=0.5", color="#3b444b", shrinkA=0),
                 bbox=dict(boxstyle="circle", facecolor="#3b444b", linewidth=2.0),
                 fontsize=100, color="white", ha="center")

    ax.set_axis_off()
    fig.patch.set_facecolor('none')  # Make the figure background transparent
    # plt.title("", loc="center", pad=20, fontsize=55, fontweight="bold");
    return fig

def linear_gauge_chart(recommendation: float):
    fig = plt.figure(figsize=(6, 2))

    ax = fig.add_axes([0.1, 0.4, 0.8, 0.2])

    bounds = [0, 1, 2, 3, 4, 5]
    labels = ('Strong Buy', 'Buy', 'Hold', 'Sell', 'Strong Sell')

    cmap = cm.Spectral_r
    norm = colors.Normalize(vmin=bounds[0], vmax=bounds[-1])

    cb = colorbar.ColorbarBase(
        ax,
        cmap=cmap,
        norm=norm,
        orientation='horizontal',
        boundaries=bounds,
    )

    for i, label in enumerate(labels):
        xpos = float((2 * i + 1)) / (2 * len(labels))
        ax.annotate(label, xy=(xpos, 0.5), xycoords='axes fraction', ha='center', va='center', color='black')


    if recommendation is not None:
        arrow_position = (recommendation + 0.5) / (len(bounds) - 1)  # Normalize the arrow position
        ax.annotate(
            '▼',  # Downward arrow
            xy=(arrow_position, -0.2),  # Position below the color bar
            xytext=(0, -10),  # Slight offset
            textcoords='offset points',
            ha='center',
            va='center',
            fontsize=16,
            color='black',
        )

    fig.patch.set_facecolor('none')  # Make the figure background transparent
    return fig