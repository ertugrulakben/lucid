"""Dark Qt style sheet for the overlay and prompt bar."""

QSS_DARK = """
#LucidOverlay {
    background-color: rgba(16, 16, 20, 252);
    border: 1px solid rgba(90, 90, 110, 255);
    border-radius: 14px;
}
#LucidPromptBar {
    background: transparent;
    color: #F2F2F7;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 20px;
    padding: 14px 18px;
    border: none;
    selection-background-color: rgba(80, 140, 255, 120);
}
#LucidResultPane {
    background: transparent;
    color: #D6D6DE;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 14px;
    padding: 8px 18px 14px 18px;
    border: none;
}
#LucidModeBar {
    background: rgba(26, 26, 32, 250);
    border-top: 1px solid rgba(70, 70, 85, 220);
    border-bottom-left-radius: 14px;
    border-bottom-right-radius: 14px;
}
#LucidModeButton {
    background: transparent;
    color: #AAA;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 12px;
    border: none;
    padding: 8px 14px;
    border-radius: 8px;
}
#LucidModeButton:hover {
    color: #FFF;
    background: rgba(80, 140, 255, 40);
}
#LucidModeButton[active="true"][mode="answer"] {
    color: #FFF;
    background: rgba(80, 140, 255, 120);
    font-weight: 600;
}
#LucidModeButton[active="true"][mode="teach"] {
    color: #FFF;
    background: rgba(255, 170, 60, 140);
    font-weight: 600;
}
#LucidModeButton[active="true"][mode="execute"] {
    color: #FFF;
    background: rgba(235, 80, 90, 150);
    font-weight: 600;
}
#LucidStatus {
    color: #888;
    font-size: 11px;
    padding: 4px 18px 10px 18px;
}
#LucidStopButton {
    background: rgba(235, 80, 90, 220);
    color: #FFF;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 12px;
    font-weight: 600;
    border: none;
    padding: 8px 14px;
    border-radius: 8px;
}
#LucidStopButton:hover {
    background: rgba(255, 100, 110, 240);
}
#LucidStopButton:pressed {
    background: rgba(200, 50, 60, 240);
}
#LucidToolbar {
    background: transparent;
}
#LucidToolbarButton {
    background: rgba(40, 40, 48, 200);
    color: #DDD;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 11px;
    border: 1px solid rgba(80, 80, 100, 180);
    padding: 4px 10px;
    border-radius: 6px;
}
#LucidToolbarButton:hover {
    background: rgba(60, 60, 80, 220);
    color: #FFF;
}
#LucidToolbarButton:checked {
    background: rgba(80, 140, 255, 140);
    color: #FFF;
    border-color: rgba(120, 170, 255, 220);
}
#LucidWindowControl {
    background: rgba(40, 40, 48, 180);
    color: #BBB;
    font-family: "Segoe UI Symbol", "Segoe UI", sans-serif;
    font-size: 13px;
    border: 1px solid rgba(80, 80, 100, 160);
    padding: 2px 0;
    border-radius: 6px;
}
#LucidWindowControl:hover {
    background: rgba(80, 140, 255, 160);
    color: #FFF;
    border-color: rgba(120, 170, 255, 220);
}
"""
