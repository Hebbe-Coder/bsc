import { useMemo } from 'react';

interface TableComponentProps {
  data: any;
  width: number;
  height: number;
}

const TableComponent = ({ data, width, height }: TableComponentProps) => {
  const columns = useMemo(() => data?.columns || [], [data]);
  const rows = useMemo(() => data?.rows || [], [data]);

  return (
    <div 
      className="overflow-auto bg-white rounded-lg shadow-sm border border-gray-200"
      style={{ width, height }}
    >
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gradient-to-r from-blue-500 to-blue-600 text-white">
            {columns.map((col: string, idx: number) => (
              <th 
                key={idx} 
                className="px-4 py-3 text-left font-semibold whitespace-nowrap"
                style={{ 
                  borderTopLeftRadius: idx === 0 ? '8px' : '0',
                  borderTopRightRadius: idx === columns.length - 1 ? '8px' : '0',
                }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row: any[], rowIdx: number) => (
            <tr 
              key={rowIdx} 
              className={`border-b border-gray-100 hover:bg-blue-50 transition-colors ${
                rowIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50'
              }`}
            >
              {row.map((cell: any, cellIdx: number) => (
                <td 
                  key={cellIdx} 
                  className="px-4 py-2 text-gray-700 whitespace-nowrap"
                >
                  {typeof cell === 'number' ? (
                    <span className="font-medium text-gray-900">{cell}</span>
                  ) : (
                    cell
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <div className="flex items-center justify-center h-full text-gray-400">
          <div className="text-center">
            <div className="text-4xl mb-2">📊</div>
            <div className="text-sm">暂无数据</div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TableComponent;