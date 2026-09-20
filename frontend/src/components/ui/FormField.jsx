import React from "react";

export default function FormField({
  label,
  id,
  name,
  type = "text",
  value,
  onChange,
  placeholder,
  required = false,
  disabled = false,
  error = null,
  helperText = null,
  icon = null,
  children,
  className = "",
  inputClassName = "",
  autoComplete,
  ...props
}) {
  const isSelect = type === "select";
  const isTextarea = type === "textarea";

  const baseInputStyles = `
    w-full px-3.5 py-2.5 bg-white border rounded-lg text-slate-900 placeholder-slate-400
    text-sm transition-all duration-150
    focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600
    disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-slate-50
    ${error ? "border-rose-500 focus:border-rose-500 focus:ring-rose-500/20" : "border-slate-300 hover:border-slate-400"}
    ${icon ? "pl-10" : ""}
    ${inputClassName}
  `;

  return (
    <div className={`space-y-1.5 ${className}`}>
      {label && (
        <label
          htmlFor={id}
          className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
        >
          {label} {required && <span className="text-rose-500">*</span>}
        </label>
      )}

      <div className="relative">
        {icon && (
          <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
            {icon}
          </div>
        )}

        {isSelect ? (
          <select
            id={id}
            name={name}
            value={value}
            onChange={onChange}
            disabled={disabled}
            required={required}
            className={`${baseInputStyles} appearance-none pr-9`}
            {...props}
          >
            {children}
          </select>
        ) : isTextarea ? (
          <textarea
            id={id}
            name={name}
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            disabled={disabled}
            required={required}
            className={baseInputStyles}
            rows={props.rows || 3}
            {...props}
          />
        ) : (
          <input
            type={type}
            id={id}
            name={name}
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            disabled={disabled}
            required={required}
            autoComplete={autoComplete}
            className={baseInputStyles}
            {...props}
          />
        )}

        {isSelect && (
          <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-slate-400">
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </div>
        )}
      </div>

      {error && (
        <p className="text-xs text-rose-400 font-medium flex items-center gap-1 mt-1">
          <svg
            className="w-3.5 h-3.5 shrink-0"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
          <span>{error}</span>
        </p>
      )}

      {helperText && !error && (
        <p className="text-xs text-slate-400 mt-1">{helperText}</p>
      )}
    </div>
  );
}
