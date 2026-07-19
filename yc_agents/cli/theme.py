YCORE_TCSS = """
Screen {
    layout: vertical;
    background: #141414;
    color: #e1e1e1;
}

#status {
    dock: top;
    height: 1;
    padding: 0 2;
    background: #0a0a0a;
    color: #a0a0a0;
}

#workbench {
    height: 1fr;
    background: #141414;
}

#sidebar {
    width: 28;
    min-width: 24;
    padding: 0 1;
    border-right: solid #242424;
    background: #111111;
}

#sidebar.hidden {
    display: none;
}

.sidebar-title {
    height: 1;
    margin-top: 1;
    padding-left: 1;
    color: #787878;
    text-style: bold;
}

#workspace-list {
    height: 7;
    margin-bottom: 1;
    background: transparent;
}

#session-list {
    height: 1fr;
    background: transparent;
}

ListView > ListItem {
    padding: 0 1;
    color: #a0a0a0;
    background: transparent;
}

ListView > ListItem:hover {
    background: #1c1c1c;
    color: #e1e1e1;
}

ListView > ListItem.-highlight {
    background: #242424;
    color: #e1e1e1;
}

ListView > ListItem.active {
    color: #e1e1e1;
    text-style: bold;
}

#main-pane {
    width: 1fr;
    height: 1fr;
    background: #141414;
}

#chat-box {
    height: 1fr;
    padding: 0 1;
    border: none;
    background: #141414;
}

#transcript {
    height: 1fr;
    padding: 1 2 0 2;
    border: none;
    background: #141414;
    scrollbar-color: #3a3a3a;
    scrollbar-background: #141414;
}

.turn-label {
    height: 1;
    padding: 0 1;
    color: #787878;
    text-style: bold;
}

.turn-body {
    height: auto;
    padding: 0 1;
    color: #e1e1e1;
}

.turn-user-label,
.turn-user-body {
    background: #242424;
    color: #c8c8c8;
}

.turn-user-label {
    color: #e1e1e1;
}

.turn-assistant-label {
    color: #bb9af7;
}

.turn-error-label {
    color: #f7768e;
}

.turn-system-label {
    color: #7aa2f7;
}

.turn-gap {
    height: 1;
}

.process-block {
    margin: 0 1;
    padding: 0 1;
    background: #1c1c1c;
    color: #a0a0a0;
    border: none;
}

#processing-elapsed {
    height: 1;
    padding: 0 2;
    color: #787878;
    background: #141414;
}

#selection-list {
    height: auto;
    max-height: 8;
    margin: 0 2;
    padding: 0 1;
    border: solid #323237;
    background: #1c1c1c;
    color: #e1e1e1;
}

#selection-list.hidden {
    display: none;
}

#prompt-area {
    height: auto;
    margin: 0 2 1 2;
    border: solid #323237;
    background: #141414;
}

#prompt-area:focus-within {
    border: solid #505058;
}

#command-suggestions {
    height: auto;
    max-height: 7;
    margin: 0 2;
    padding: 0 1;
    border: solid #323237;
    background: #1c1c1c;
    color: #a0a0a0;
}

#prompt {
    height: 1;
    padding: 0 1;
    border: none;
    background: #141414;
    color: #e1e1e1;
}

#prompt > .input--placeholder {
    color: #6c6c6c;
}

#prompt > .input--cursor {
    background: #e1e1e1;
    color: #141414;
    text-style: none;
}

#prompt-meta {
    height: 1;
    padding: 0 1;
    color: #787878;
    background: #141414;
}
"""
