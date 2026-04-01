/**
 * api.js - Mock API 服务层
 * 后期直接替换为真实后端接口调用即可
 */

const API_BASE = '/api';

// ===== 模拟数据 =====
const _mockModels = [
    { id: 1,  title: '拉虾虾 天妇罗炸虾 拉布布 labubu',         author: 'MW用户A', downloads: 842, likes: 312, tags: ['玩具','手办'],    description: '高度详细的免支撑3D模型，专为Bambu Lab打印机优化。基础版本无需AMS即可打印。具有卡扣接合和优化的悬垂结构。', source_url: '' },
    { id: 2,  title: '盖瑞血清笔丨疯狂动物城2盖瑞笔（无AMS）',    author: 'BambuPlayer', downloads: 567, likes: 203, tags: ['工具'],       description: '灵感来自疯狂动物城2的盖瑞角色，造型精致可爱，支持无AMS打印。', source_url: '' },
    { id: 3,  title: '手工材料模块化收纳盒',                     author: 'SonicMint',  downloads: 1240, likes: 458, tags: ['收纳','工具'],  description: '可自由组合的模块化收纳系统，适合各类手工材料的分类收纳。每个模块独立打印，可灵活堆叠。', source_url: '' },
    { id: 4,  title: '可堆叠零件盘 - 手办零件收纳分类',           author: 'MakerJoe',   downloads: 983, likes: 367, tags: ['收纳'],         description: '专为手办零件分类设计的可堆叠托盘，多层叠放节省空间。底部带有防滑纹理设计。', source_url: '' },
    { id: 5,  title: '小野盲盒潮玩泰迪熊泡泡玛特全分件',          author: '3DEnt',      downloads: 2150, likes: 891, tags: ['手办','艺术'],  description: '高精度全分件盲盒泰迪熊模型，新手友好设计。所有部件可独立打印后组装上色。', source_url: '' },
    { id: 6,  title: '七龙珠之火焰山龟仙人 Master Roshi',         author: 'BambuPlayer', downloads: 1876, likes: 720, tags: ['手办','艺术'],  description: '经典七龙珠角色龟仙人高精度打印模型，包含完整底座和动态姿势设计。', source_url: '' },
    { id: 7,  title: '浴室肥皂和洗发水托盘',                     author: 'SonicMint',  downloads: 456, likes: 189, tags: ['工具','收纳'],   description: '实用的浴室收纳解决方案，底部带排水孔设计，适合各种规格的洗浴用品。', source_url: '' },
    { id: 8,  title: '六层抽屉收纳盒',                           author: 'MakerJoe',   downloads: 1600, likes: 534, tags: ['收纳'],         description: '紧凑六层抽屉柜，适合桌面小物件收纳。抽屉滑轨经过优化，顺滑无卡顿。', source_url: '' },
    { id: 9,  title: 'AMS2 PRO 机甲风干燥盒',                    author: '3DEnt',      downloads: 3200, likes: 1200, tags: ['工具'],        description: '为AMS2 PRO设计的干燥盒外壳，机甲科幻风格外观，内置硅胶干燥剂槽位。', source_url: '' },
    { id: 10, title: '周杰伦-周同学年度巨献-网球周手办',            author: 'BambuPlayer', downloads: 4500, likes: 2100, tags: ['手办','艺术'], description: '高仿真周杰伦网球造型手办模型，全分件设计，可多色打印无需AMS。', source_url: '' },
    { id: 11, title: '像素挂钩 - 模块化墙壁挂钩系统',              author: 'SonicMint',  downloads: 780, likes: 290, tags: ['工具','收纳'],   description: '像素风格的模块化墙壁挂钩系统，可自由拼接图案，兼具实用性与装饰性。', source_url: '' },
    { id: 12, title: '索尼克·音速小子 分色拼装 NO AMS',            author: 'MakerJoe',   downloads: 2800, likes: 1050, tags: ['手办','玩具'], description: '经典索尼克角色全分件分色打印模型，无需AMS和胶水即可完成组装。', source_url: '' },
];

// ===== API 封装 =====
window.ApiService = {
    /**
     * 获取模型列表
     * @param {Object} params - { keyword, page, pageSize }
     */
    async getModels(params = {}) {
        // Mock: 模拟 200ms 网络延迟
        await new Promise(r => setTimeout(r, 200));
        let list = [..._mockModels];
        if (params.keyword) {
            const kw = params.keyword.toLowerCase();
            list = list.filter(m => m.title.toLowerCase().includes(kw) || m.tags.some(t => t.includes(kw)));
        }
        return { code: 0, data: list, total: list.length };
    },

    /**
     * 获取模型详情
     * @param {number|string} id
     */
    async getModelDetail(id) {
        await new Promise(r => setTimeout(r, 150));
        const model = _mockModels.find(m => m.id === Number(id));
        if (!model) return { code: 404, message: '模型不存在' };
        return { code: 0, data: { ...model } };
    },

    /**
     * 更新模型信息
     * @param {number|string} id
     * @param {Object} updates
     */
    async updateModel(id, updates) {
        await new Promise(r => setTimeout(r, 300));
        const idx = _mockModels.findIndex(m => m.id === Number(id));
        if (idx === -1) return { code: 404, message: '模型不存在' };
        Object.assign(_mockModels[idx], updates);
        return { code: 0, data: { ..._mockModels[idx] } };
    },

    /**
     * 获取配置
     */
    async getConfig() {
        await new Promise(r => setTimeout(r, 100));
        return {
            code: 0,
            data: {
                download_dir: './data',
                cookie_file: './config/cookie.json',
                logs_dir: './logs',
                local_batch_import: { enabled: true, watch_dirs: ['./watch'], scan_interval_seconds: 30 },
                notifications: { telegram: { enable_push: true }, wecom: { enable_push: false } },
                folder_open: { enabled: true, open_mode: 'client' }
            }
        };
    },

    /**
     * 保存配置
     * @param {Object} config
     */
    async saveConfig(config) {
        await new Promise(r => setTimeout(r, 400));
        return { code: 0, message: '保存成功' };
    },

    /**
     * 打开模型文件夹
     * @param {number|string} id
     */
    async openFolder(id) {
        await new Promise(r => setTimeout(r, 200));
        return { code: 0, message: '已发送打开请求' };
    }
};
