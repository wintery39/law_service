import { Link } from 'react-router-dom';
import { EmptyState } from '../components/common/EmptyState';

export default function NotFoundPage() {
  return (
    <EmptyState
      title="요청한 화면을 찾을 수 없습니다."
      description="경로가 잘못되었거나 접근할 수 없는 페이지입니다. 대시보드로 돌아가 다시 시작해 주세요."
      action={
        <Link to="/" className="rounded-full bg-navy-900 px-4 py-2 text-sm font-semibold text-white">
          대시보드로 이동
        </Link>
      }
    />
  );
}
