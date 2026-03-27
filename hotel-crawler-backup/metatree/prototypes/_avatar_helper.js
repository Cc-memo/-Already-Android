// 通用的头像加载函数，可以在所有页面使用
// 加载用户头像到右上角
function loadUserAvatar(userId) {
    try {
        const userData = JSON.parse(localStorage.getItem('user_avatar') || '{}');
        const avatarData = userId ? (userData[userId] || userData['default']) : userData['default'];
        const headerAvatar = document.getElementById('headerUserAvatar') || document.querySelector('.user-avatar');
        
        if (headerAvatar) {
            if (avatarData) {
                headerAvatar.innerHTML = `<img src="${avatarData}" alt="User Avatar">`;
            } else {
                headerAvatar.innerHTML = `<i class="fas fa-user"></i>`;
            }
        }
    } catch (error) {
        console.error('加载头像失败:', error);
    }
}
