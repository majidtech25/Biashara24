# Biashara360 print program

The system runs on a cloud server, which cannot reach printers on a branch's own network.
This small program runs on a computer at the branch. Every few seconds it collects that
branch's kitchen tickets from the server and prints them on the local network.

It needs **Python 3.9 or newer** and nothing else. Any computer on the same network as the
printers will do, as long as it stays on during opening hours: the office PC, a small
Linux box or a Raspberry Pi.

## 1. Add the computer in the system

1. Sign in as a manager or director and open **Printers**.
2. Check each department's printer address (and, for more than one branch, the
   **Printers per branch** list). The program prints to these addresses.
3. Under **Print program at each branch**, choose the branch, type a name such as
   "Kitchen PC" and save. Copy the **key** that appears. It is shown only once; if it is lost,
   remove that computer and add it again.

From now on, that branch's tickets wait on the server until the program collects them.

## 2. Install on Windows

1. Install Python from https://www.python.org/downloads/windows/ (tick "Add python.exe to PATH").
2. Copy this folder to the computer, for example `C:\Biashara360\print-agent`.
3. Copy `print_agent.ini.example` to `print_agent.ini` and fill in the server address and the key.
4. Double-click `start_print_agent.bat`. It shows each ticket it prints and restarts by itself
   if it stops.
5. To start it automatically, open **Task Scheduler** → **Create Basic Task** → trigger
   **When I log on** (or **When the computer starts**) → action **Start a program** →
   `C:\Biashara360\print-agent\start_print_agent.bat`.

## 2. Install on Linux or a Raspberry Pi

```bash
sudo mkdir -p /opt/biashara-print-agent
sudo cp print_agent.py biashara-print-agent.service /opt/biashara-print-agent/
sudo cp print_agent.ini.example /opt/biashara-print-agent/print_agent.ini
sudo nano /opt/biashara-print-agent/print_agent.ini          # server address and key
sudo chmod 600 /opt/biashara-print-agent/print_agent.ini
sudo cp /opt/biashara-print-agent/biashara-print-agent.service /etc/systemd/system/
sudo systemctl enable --now biashara-print-agent
journalctl -u biashara-print-agent -f                       # see tickets as they print
```

## 3. Check it works

Send a test order to a table. Within a few seconds the ticket prints, and on the **Printers**
page the computer shows **Connected** with a recent "Last checked in" time.

## What happens when something goes wrong

- **Printer off or unplugged:** nothing was printed, so the program tries again automatically
  for up to 30 minutes (5 tries).
- **Printing broke off halfway:** part of the ticket may have printed. It is never printed
  again automatically. A manager checks with the kitchen and reprints from
  **Printer Recovery**; the program then prints the copy.
- **Internet down at the branch:** tickets wait on the server and print once the connection
  is back. Tickets older than 12 hours are left for Printer Recovery instead.
- **Computer replaced or key leaked:** remove the computer on the Printers page (its key stops
  working at once) and add the new one.
- **Program removed and none left for a branch:** the server goes back to sending that branch's
  tickets directly, which only works if the server is on the branch's network.

## Settings

Instead of `print_agent.ini`, the environment variables `BIASHARA_SERVER` and
`BIASHARA_PRINT_KEY` can be used. `python print_agent.py --once` collects and prints once and
then stops, which is handy for a first test.
