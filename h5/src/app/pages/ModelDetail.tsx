import { useEffect, useRef, useState, type SyntheticEvent } from 'react';
import { useParams, useNavigate } from 'react-router';
import { 
  ChevronLeft, ExternalLink, RefreshCw, 
  FileText, Box, Clock, Scale, Printer, FileDown, Eye, FileDigit, Image as ImageIcon, FileBox, X
} from 'lucide-react';
import { getModelDetail } from '../lib/mobile-api';
import type { MobileInstance, MobileModelDetail } from '../types/mobile';

export function ModelDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [selectedInstance, setSelectedInstance] = useState<MobileInstance | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [model, setModel] = useState<MobileModelDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const loadModel = async (modelId: string) => {
    setIsLoading(true);
    setError('');
    try {
      const payload = await getModelDetail(modelId);
      setModel(payload);
      setCurrentImageIndex(0);
    } catch (err: unknown) {
      setModel(null);
      setError(err instanceof Error ? err.message : '加载失败，请稍后重试');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!id) {
      setIsLoading(false);
      setModel(null);
      setError('未提供模型标识');
      return;
    }
    loadModel(id);
  }, [id]);

  // Sync scroll position to active index
  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    const width = scrollContainerRef.current.clientWidth;
    const scrollLeft = scrollContainerRef.current.scrollLeft;
    const newIndex = Math.round(scrollLeft / width);
    if (newIndex !== currentImageIndex) {
      setCurrentImageIndex(newIndex);
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-slate-50 p-5">
        <RefreshCw size={48} className="text-slate-300 mb-4 animate-spin" />
        <h2 className="text-lg font-bold text-slate-800">正在加载模型</h2>
      </div>
    );
  }

  if (!model) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-slate-50 p-5">
        <Box size={48} className="text-slate-300 mb-4" />
        <h2 className="text-lg font-bold text-slate-800">{error || '未找到模型'}</h2>
        <button onClick={() => navigate(-1)} className="mt-4 text-blue-600 font-medium px-4 py-2 bg-blue-50 rounded-xl">返回上一页</button>
      </div>
    );
  }

  const SectionTitle = ({ title, icon: Icon }: { title: string, icon: any }) => (
    <div className="flex items-center gap-2 mb-3 mt-6 px-1">
      <Icon size={18} className="text-blue-600" />
      <h3 className="text-base font-bold text-slate-800">{title}</h3>
    </div>
  );

  const images = Array.from(new Set(model.images && model.images.length > 0 ? model.images : [model.coverImage].filter(Boolean)));
  const imageFallback = 'https://placehold.co/160x160/e2e8f0/64748b?text=3D';
  const plateFallback = 'https://placehold.co/96x96/e2e8f0/64748b?text=Plate';

  const renderMetricText = (value?: string, fallback = '未记录') => {
    const text = (value || '').trim();
    return text || fallback;
  };

  const bindImageFallback = (fallback: string) => ({
    onError: (event: SyntheticEvent<HTMLImageElement>) => {
      const target = event.currentTarget;
      if (target.dataset.fallbackApplied === '1') {
        return;
      }
      target.dataset.fallbackApplied = '1';
      target.src = fallback;
    },
  });

  const buildInstanceMeta = (instance: MobileInstance) => {
    return [instance.printer, instance.layerHeight, instance.material].map((item) => (item || '').trim()).filter(Boolean);
  };

  const getFileIcon = (type: string) => {
    switch(type) {
      case '3mf': return <FileBox size={24} className="text-indigo-500" />;
      case 'stl': return <Box size={24} className="text-emerald-500" />;
      case 'pdf': return <FileText size={24} className="text-rose-500" />;
      case 'image': return <ImageIcon size={24} className="text-blue-500" />;
      default: return <FileDigit size={24} className="text-slate-500" />;
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 dark:bg-slate-950 relative pb-10 transition-colors">
      {/* Header - Sticky */}
      <header className="fixed top-0 left-0 right-0 max-w-md mx-auto w-full z-50 px-4 pt-12 pb-3 flex items-center justify-between pointer-events-none">
        <button 
          onClick={() => navigate(-1)}
          className="w-10 h-10 rounded-full bg-black/30 backdrop-blur-md border border-white/10 flex items-center justify-center text-white pointer-events-auto transition-transform active:scale-90 shadow-sm"
        >
          <ChevronLeft size={24} />
        </button>
        <div className="flex gap-2 pointer-events-auto">
          <button
            onClick={() => {
              if (id) {
                loadModel(id);
              }
            }}
            className="w-10 h-10 rounded-full bg-black/30 backdrop-blur-md border border-white/10 flex items-center justify-center text-white transition-transform active:scale-90 shadow-sm"
          >
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      {/* Hero Image Carousel */}
      <div className="relative w-full aspect-square bg-slate-900 group">
        <div 
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="w-full h-full flex overflow-x-auto snap-x snap-mandatory hide-scrollbar"
        >
          {images.map((img, idx) => (
            <div key={idx} className="w-full h-full shrink-0 snap-center relative">
              <img
                src={img || 'https://placehold.co/1024x1024/0f172a/e2e8f0?text=3D'}
                alt={`${model.title} ${idx + 1}`}
                className="w-full h-full object-cover"
                {...bindImageFallback(imageFallback)}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/20" />
            </div>
          ))}
        </div>
        
        {/* Pagination Dots */}
        {images.length > 1 && (
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-black/30 backdrop-blur-sm px-2.5 py-1.5 rounded-full">
            {images.map((_, idx) => (
              <div 
                key={idx} 
                className={`transition-all duration-300 rounded-full ${
                  idx === currentImageIndex ? 'w-3 h-1.5 bg-white' : 'w-1.5 h-1.5 bg-white/50'
                }`}
              />
            ))}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="px-5 py-6 relative -mt-6 bg-slate-50 dark:bg-slate-950 rounded-t-3xl shadow-[0_-8px_30px_rgba(0,0,0,0.12)] transition-colors">
        
        {/* Title & Author */}
        <div className="mb-4">
          <h1 className="text-xl font-bold text-slate-900 dark:text-white leading-snug mb-1">{model.title}</h1>
          {model.author && (
            <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">by {model.author}</p>
          )}
        </div>

        {/* Source & Date Row */}
        <div className="flex flex-wrap items-center gap-2 mb-6">
          {model.source && (
            <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-2.5 py-1 rounded-md font-medium border border-slate-200 dark:border-slate-700">
              {model.source}
            </span>
          )}
          {model.createdAt && (
            <span className="text-xs text-slate-400 font-medium">
              采集时间：{model.createdAt}
            </span>
          )}
        </div>

        {/* Action Buttons */}
        <div className="mb-6">
          <button
            onClick={() => {
              if (model.sourceUrl) {
                window.open(model.sourceUrl, '_blank', 'noopener,noreferrer');
              }
            }}
            disabled={!model.sourceUrl}
            className="w-full bg-blue-600 text-white font-semibold py-3.5 rounded-xl flex items-center justify-center gap-2 active:bg-blue-700 transition-colors shadow-sm shadow-blue-200"
          >
            <ExternalLink size={18} /> {model.sourceUrl ? '打开源网页' : '暂无源链接'}
          </button>
        </div>

        {/* Description */}
        {(model.descriptionHtml || model.description) && (
          <div>
            <SectionTitle title="模型简介" icon={FileText} />
            <div className="bg-white dark:bg-slate-900 rounded-[28px] border border-slate-100 dark:border-slate-800 shadow-sm overflow-hidden transition-colors">
              {model.descriptionHtml ? (
                <div
                  className="mobile-rich-content px-5 py-5 text-[15px] text-slate-700"
                  dangerouslySetInnerHTML={{ __html: model.descriptionHtml }}
                />
              ) : (
                <div className="px-5 py-5 text-[15px] text-slate-700 leading-8 whitespace-pre-wrap">
                  {model.description}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Instances / Configs */}
        <div>
          <SectionTitle title="配置详情" icon={Box} />
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm overflow-hidden divide-y divide-slate-50 dark:divide-slate-800 transition-colors">
            {model.instances && model.instances.length > 0 ? (
               model.instances.map((instance, idx) => (
                <div key={idx} className="p-3 flex items-center gap-3 hover:bg-slate-50 transition-colors">
                  <img
                    src={instance.image || model.coverImage || imageFallback}
                    alt=""
                    className="w-16 h-16 rounded-xl object-cover bg-slate-100 shrink-0 border border-slate-100"
                    {...bindImageFallback(model.coverImage || imageFallback)}
                  />
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-bold text-slate-800 leading-snug line-clamp-2">{instance.name}</h4>
                    {instance.summary && (
                      <div className="text-[11px] text-slate-500 mt-1 line-clamp-2">{instance.summary}</div>
                    )}
                    {buildInstanceMeta(instance).length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {buildInstanceMeta(instance).map((item) => (
                          <span key={item} className="bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-2 py-0.5 rounded-md text-[10px] font-medium border border-slate-200 dark:border-slate-700">
                            {item}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-500 font-medium">
                      <span className="flex items-center gap-1"><Clock size={10} className="text-slate-400" /> {renderMetricText(instance.time)}</span>
                      <span className="flex items-center gap-1"><Scale size={10} className="text-slate-400" /> {renderMetricText(instance.weight)}</span>
                    </div>
                  </div>
                  <button 
                    onClick={() => setSelectedInstance(instance)}
                    className="px-3.5 py-1.5 bg-blue-50 text-blue-600 text-xs font-semibold rounded-lg hover:bg-blue-100 active:scale-95 transition-all shrink-0"
                  >
                    详情
                  </button>
                </div>
              ))
            ) : (
              <div className="p-6 flex flex-col items-center justify-center text-slate-400">
                <Box size={32} className="mb-2 opacity-50" />
                <p className="text-xs font-medium">暂无打印配置文件</p>
              </div>
            )}
          </div>
        </div>

        {/* Attachments - Moved to bottom */}
        {model.attachments && model.attachments.length > 0 && (
          <div>
            <SectionTitle title="附件" icon={FileBox} />
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm overflow-hidden divide-y divide-slate-50 dark:divide-slate-800 transition-colors">
              {model.attachments.map((file, idx) => (
                <div key={idx} className="p-4 flex items-center gap-3 hover:bg-slate-50 transition-colors">
                  <div className="p-2.5 bg-slate-50 rounded-xl shrink-0">
                    {getFileIcon(file.type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-slate-800 truncate">{file.name}</div>
                    <div className="text-[11px] text-slate-500 mt-0.5 uppercase">{file.type}</div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {file.type === 'image' && (
                      <button
                        onClick={() => {
                          if (file.url) {
                            window.open(file.url, '_blank', 'noopener,noreferrer');
                          }
                        }}
                        className="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 bg-slate-50 hover:bg-slate-100 active:scale-95 transition-all"
                      >
                        <Eye size={16} />
                      </button>
                    )}
                    <button
                      onClick={() => {
                        if (file.url) {
                          window.open(file.url, '_blank', 'noopener,noreferrer');
                        }
                      }}
                      className="w-8 h-8 rounded-full flex items-center justify-center text-blue-500 bg-blue-50 hover:bg-blue-100 active:scale-95 transition-all"
                    >
                      <FileDown size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>

      {/* Configuration Details Modal */}
      <div 
        className={`fixed inset-0 z-[100] flex justify-center items-end bg-black/40 backdrop-blur-sm transition-opacity duration-300 ${selectedInstance ? 'opacity-100' : 'opacity-0 pointer-events-none'}`} 
        onClick={() => setSelectedInstance(null)}
      >
        <div 
          className={`w-full max-w-md bg-white dark:bg-slate-900 rounded-t-3xl overflow-hidden transition-transform duration-300 transform max-h-[calc(100dvh-68px)] mb-[68px] flex flex-col ${selectedInstance ? 'translate-y-0' : 'translate-y-full'}`} 
          onClick={e => e.stopPropagation()}
        >
          {/* Modal Header */}
          <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between shrink-0">
            <h3 className="font-bold text-slate-900 dark:text-white text-lg">配置详情</h3>
            <button onClick={() => setSelectedInstance(null)} className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 active:scale-95 transition-all">
              <X size={18} />
            </button>
          </div>
          
          {/* Modal Content */}
          {selectedInstance && (
            <div className="p-5 overflow-y-auto min-h-0 flex-1">
              <div className="flex gap-4 mb-6 bg-slate-50 p-4 rounded-2xl border border-slate-100">
                <img
                  src={selectedInstance.image || model.coverImage || imageFallback}
                  alt=""
                  className="w-20 h-20 rounded-xl object-cover shrink-0 bg-white border border-slate-100"
                  {...bindImageFallback(model.coverImage || imageFallback)}
                />
                <div className="flex-1 min-w-0">
                  <h4 className="font-bold text-slate-900 text-lg leading-snug mb-2">{selectedInstance.name}</h4>
                  {selectedInstance.summary && (
                    <p className="text-sm text-slate-600 leading-relaxed mb-3">{selectedInstance.summary}</p>
                  )}
                  {buildInstanceMeta(selectedInstance).length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {buildInstanceMeta(selectedInstance).map((item) => (
                        <span key={item} className="bg-white border border-slate-200 px-2 py-1 rounded-lg text-[11px] text-slate-600 font-medium">{item}</span>
                      ))}
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded-xl bg-white border border-slate-200 px-3 py-2">
                      <div className="flex items-center gap-1 text-slate-400 mb-1"><Clock size={12} /> 打印时长</div>
                      <div className="font-semibold text-slate-700">{renderMetricText(selectedInstance.time)}</div>
                    </div>
                    <div className="rounded-xl bg-white border border-slate-200 px-3 py-2">
                      <div className="flex items-center gap-1 text-slate-400 mb-1"><Scale size={12} /> 耗材重量</div>
                      <div className="font-semibold text-slate-700">{renderMetricText(selectedInstance.weight)}</div>
                    </div>
                  </div>
                </div>
              </div>

              <h5 className="font-bold text-slate-800 text-sm mb-3">包含分盘 ({selectedInstance.plates?.length || 0})</h5>
              <div className="space-y-3">
                {selectedInstance.plates?.map((plate, idx) => (
                  <div key={idx} className="p-3 bg-white border border-slate-200 rounded-2xl shadow-sm">
                     <div className="flex items-start gap-3">
                       <img
                         src={plate.image || plateFallback}
                         alt=""
                         className="w-16 h-16 rounded-xl object-cover bg-slate-50 shrink-0 border border-slate-100"
                         {...bindImageFallback(plateFallback)}
                       />
                       <div className="flex-1 min-w-0">
                         <div className="flex items-start justify-between gap-3">
                           <div>
                             <div className="font-bold text-slate-800 text-sm">{plate.name}</div>
                             <div className="text-[11px] text-slate-400 mt-1">分盘配置</div>
                           </div>
                           <div className="text-right shrink-0">
                             <div className="text-[11px] text-slate-400">打印时长</div>
                             <div className="text-sm font-semibold text-slate-700">{renderMetricText(plate.time)}</div>
                           </div>
                         </div>
                         <div className="flex items-center justify-between gap-3 mt-3">
                           <div className="min-w-0">
                             <div className="text-[11px] text-slate-400 mb-1">耗材颜色</div>
                             {plate.materials.length > 0 ? (
                               <div className="flex flex-wrap items-center gap-2">
                                 {plate.materials.map((color, i) => (
                                   <div key={`${color}-${i}`} className="flex items-center gap-1.5 rounded-full bg-slate-50 border border-slate-200 px-2 py-1">
                                     <div className="w-3 h-3 rounded-full border border-black/10 shadow-inner" style={{ backgroundColor: color }} />
                                     <span className="text-[10px] text-slate-500 font-medium">{color}</span>
                                   </div>
                                 ))}
                               </div>
                             ) : (
                               <div className="text-[11px] text-slate-400">无耗材颜色数据</div>
                             )}
                           </div>
                           <div className="text-right shrink-0">
                             <div className="text-[11px] text-slate-400">耗材重量</div>
                             <div className="text-sm font-semibold text-slate-700">{renderMetricText(plate.weight)}</div>
                           </div>
                         </div>
                       </div>
                     </div>
                  </div>
                ))}
                {(!selectedInstance.plates || selectedInstance.plates.length === 0) && (
                  <div className="text-center py-6 text-slate-400 text-xs">
                    该配置没有单独的分盘信息
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        .hide-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .hide-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
        .pb-safe {
          padding-bottom: env(safe-area-inset-bottom, 20px);
        }
        .mobile-rich-content {
          line-height: 1.9;
          word-break: break-word;
        }
        .mobile-rich-content > *:first-child {
          margin-top: 0;
        }
        .mobile-rich-content > *:last-child {
          margin-bottom: 0;
        }
        .mobile-rich-content p {
          margin: 0 0 1rem;
          color: #475569;
          font-size: 0.98rem;
        }
        .mobile-rich-content h1,
        .mobile-rich-content h2,
        .mobile-rich-content h3,
        .mobile-rich-content h4 {
          margin: 1.5rem 0 0.75rem;
          color: #0f172a;
          font-weight: 800;
          line-height: 1.4;
        }
        .mobile-rich-content ul,
        .mobile-rich-content ol {
          margin: 0 0 1rem;
          padding-left: 1.25rem;
          color: #475569;
        }
        .mobile-rich-content li + li {
          margin-top: 0.45rem;
        }
        .mobile-rich-content hr {
          border: none;
          border-top: 1px dashed #cbd5e1;
          margin: 1.4rem 0;
        }
        .mobile-rich-content figure {
          margin: 1.15rem 0 1.4rem;
          border-radius: 1.25rem;
          overflow: hidden;
          background: #f8fafc;
          border: 1px solid #e2e8f0;
        }
        .mobile-rich-content figure.image {
          box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
        }
        .mobile-rich-content img {
          display: block;
          width: 100%;
          height: auto;
          border-radius: 1.25rem;
        }
        .mobile-rich-content .mw-video-embed {
          position: relative;
          width: 100%;
          padding-top: 56.25%;
          margin: 1.15rem 0 1.4rem;
          border-radius: 1.25rem;
          overflow: hidden;
          background: #0f172a;
          box-shadow: 0 12px 30px rgba(15, 23, 42, 0.18);
        }
        .mobile-rich-content .mw-video-embed iframe {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          border: 0;
        }
        .mobile-rich-content blockquote {
          margin: 1rem 0;
          padding: 0.9rem 1rem;
          border-left: 3px solid #3b82f6;
          background: linear-gradient(180deg, rgba(239, 246, 255, 0.9), rgba(248, 250, 252, 0.95));
          border-radius: 0 1rem 1rem 0;
          color: #334155;
        }
        .mobile-rich-content a {
          color: #2563eb;
          text-decoration: none;
          font-weight: 600;
        }
        .mobile-rich-content .mw-rich-link {
          display: inline-flex;
          align-items: center;
          gap: 0.4rem;
          padding: 0.7rem 0.9rem;
          margin: 0.4rem 0 1rem;
          background: #eff6ff;
          border: 1px solid #bfdbfe;
          border-radius: 0.95rem;
        }
        .mobile-rich-content .mw-rich-link::before {
          content: '▶';
          font-size: 0.75rem;
        }
        .mobile-rich-content .mw-boost-box {
          display: block;
          margin: 1.25rem 0 0;
          padding: 1rem 1rem 0.95rem;
          border-radius: 1.1rem;
          background: linear-gradient(135deg, #eff6ff, #f8fafc);
          border: 1px solid #dbeafe;
        }
        .mobile-rich-content .mw-boost-title {
          display: block;
          margin-bottom: 0.45rem;
          color: #1d4ed8;
          font-weight: 800;
        }
        .mobile-rich-content .mw-boost-content {
          display: block;
          color: #475569;
        }
        .dark .mobile-rich-content p,
        .dark .mobile-rich-content ul,
        .dark .mobile-rich-content ol,
        .dark .mobile-rich-content .mw-boost-content {
          color: #cbd5e1;
        }
        .dark .mobile-rich-content h1,
        .dark .mobile-rich-content h2,
        .dark .mobile-rich-content h3,
        .dark .mobile-rich-content h4 {
          color: #f8fafc;
        }
        .dark .mobile-rich-content hr {
          border-top-color: #334155;
        }
        .dark .mobile-rich-content figure {
          background: #0f172a;
          border-color: #1e293b;
        }
        .dark .mobile-rich-content blockquote {
          color: #cbd5e1;
          background: linear-gradient(180deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.98));
          border-left-color: #60a5fa;
        }
        .dark .mobile-rich-content a {
          color: #60a5fa;
        }
        .dark .mobile-rich-content .mw-rich-link {
          background: rgba(37, 99, 235, 0.12);
          border-color: rgba(96, 165, 250, 0.22);
        }
        .dark .mobile-rich-content .mw-boost-box {
          background: linear-gradient(135deg, rgba(30, 41, 59, 0.92), rgba(15, 23, 42, 0.96));
          border-color: rgba(96, 165, 250, 0.2);
        }
        .dark .mobile-rich-content .mw-boost-title {
          color: #93c5fd;
        }
      `}</style>
    </div>
  );
}
