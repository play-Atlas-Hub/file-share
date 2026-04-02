// Load leaderboard on page load
document.addEventListener('DOMContentLoaded', async () => {
    const leaderboardBody = document.getElementById('leaderboard-body');
    if (leaderboardBody) {
        try {
            const response = await fetch('/api/leaderboard');
            const data = await response.json();
            
            data.forEach((player, index) => {
                const row = `<tr>
                    <td>${index + 1}</td>
                    <td>${player.username}</td>
                    <td>${player.total_kills}</td>
                    <td>${player.total_money}</td>
                    <td>Rank ${player.current_rank}</td>
                </tr>`;
                leaderboardBody.innerHTML += row;
            });
        } catch (error) {
            console.error('Failed to load leaderboard:', error);
        }
    }
});

// WebSocket connection for game
class GameClient {
    constructor(serverUrl, loginServerUrl) {
        this.serverUrl = serverUrl;
        this.loginServerUrl = loginServerUrl;
        this.gameWs = null;
        this.loginWs = null;
        this.token = null;
        this.playerId = null;
    }

    async login(username, password) {
        return new Promise((resolve, reject) => {
            this.loginWs = new WebSocket(this.loginServerUrl);
            
            this.loginWs.onopen = () => {
                this.loginWs.send(JSON.stringify({
                    action: 'login',
                    username: username,
                    password: password
                }));
            };

            this.loginWs.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.success) {
                    this.token = data.token;
                    this.loginWs.close();
                    resolve(data);
                } else {
                    reject(data.error);
                }
            };

            this.loginWs.onerror = () => {
                reject('Login server error');
            };
        });
    }

    connectToGame() {
        return new Promise((resolve, reject) => {
            this.gameWs = new WebSocket(this.serverUrl);
            
            this.gameWs.onopen = () => {
                const username = localStorage.getItem('username');
                this.gameWs.send(JSON.stringify({
                    type: 'join_lobby',
                    username: username,
                    token: this.token
                }));
            };

            this.gameWs.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleGameMessage(data);
                resolve(this);
            };

            this.gameWs.onerror = () => {
                reject('Game server error');
            };
        });
    }

    handleGameMessage(data) {
        switch(data.type) {
            case 'welcome':
                this.playerId = data.player_id;
                console.log('Connected as player', this.playerId);
                break;
            case 'state':
                this.updateGameState(data);
                break;
            case 'chat':
                console.log(`[${data.username}] ${data.message}`);
                break;
        }
    }

    updateGameState(data) {
        // Update game rendering
        console.log('Game state updated:', data);
    }

    send(message) {
        if (this.gameWs && this.gameWs.readyState === WebSocket.OPEN) {
            this.gameWs.send(JSON.stringify(message));
        }
    }

    move(vx, vy) {
        this.send({type: 'move', vx, vy});
    }

    shoot(angle) {
        this.send({type: 'shoot', angle});
    }

    chat(message) {
        this.send({type: 'chat', message});
    }

    buyTank(tankName) {
        this.send({type: 'buy_tank', tank_name: tankName});
    }

    buyUpgrade(upgradeName) {
        this.send({type: 'buy_upgrade', upgrade_name: upgradeName});
    }
}

// Initialize game client
const gameClient = new GameClient('ws://localhost:8765', 'ws://localhost:8766');