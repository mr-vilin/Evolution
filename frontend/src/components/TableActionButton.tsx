import { forwardRef, useRef, useState, type ComponentRef } from 'react';
import { Button, Tooltip, type ButtonProps } from 'antd';

type TableActionButtonProps = ButtonProps & { tooltip: string };

export const TableActionButton = forwardRef<ComponentRef<typeof Button>, TableActionButtonProps>(
  function TableActionButton({ tooltip, onClick, onMouseMove, onFocus, onBlur, className, ...props }, ref) {
    const [open, setOpen] = useState(false);
    const dismissed = useRef(false);
    const focusRestored = useRef(false);

    return <Tooltip title={tooltip} trigger={['hover', 'focus']} open={open} destroyOnHidden
      onOpenChange={next => setOpen(next && !dismissed.current)}>
      <Button {...props} ref={ref} type="text" className={['table-action-button', className].filter(Boolean).join(' ')}
        onClick={event => {
          dismissed.current = true;
          focusRestored.current = false;
          setOpen(false);
          onClick?.(event);
        }}
        onMouseMove={event => {
          // 弹窗关闭后的焦点恢复或悬停事件不能重新触发提示。
          if (dismissed.current) {
            dismissed.current = false;
            setOpen(true);
          }
          onMouseMove?.(event);
        }}
        onFocus={event => {
          if (dismissed.current) focusRestored.current = true;
          onFocus?.(event);
        }}
        onBlur={event => {
          if (focusRestored.current) {
            dismissed.current = false;
            focusRestored.current = false;
          }
          onBlur?.(event);
        }} />
    </Tooltip>;
  },
);
