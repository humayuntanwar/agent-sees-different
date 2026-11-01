# source me: isolated X display + session bus + AT-SPI for the experiment
export DISPLAY=:9
pgrep -f "Xvfb :9 " >/dev/null || (Xvfb :9 -screen 0 1280x900x24 -ac >/tmp/xvfb9.log 2>&1 &)
sleep 1
if [ ! -f /tmp/ad-bus.env ]; then dbus-launch --sh-syntax > /tmp/ad-bus.env; fi
. /tmp/ad-bus.env
export XDG_RUNTIME_DIR=/tmp/ad-runtime; mkdir -p $XDG_RUNTIME_DIR; chmod 700 $XDG_RUNTIME_DIR
pgrep -f at-spi-bus-launcher >/dev/null || (/usr/libexec/at-spi-bus-launcher --launch-immediately >/tmp/atspi.log 2>&1 &)
export AGENT_DESKTOP_HOME=/tmp/ad-home; mkdir -p $AGENT_DESKTOP_HOME; chmod 700 $AGENT_DESKTOP_HOME
export PATH="$(npm prefix -g)/bin:$PATH"   # agent-desktop via: npm i -g agent-desktop
pgrep -f "xfwm4 --compositor=off --display :9" >/dev/null || (xfwm4 --compositor=off --display :9 >/tmp/xfwm9.log 2>&1 &)
